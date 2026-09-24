"""Atomic persistence for complete imported playlist snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Any

from symphonia.domain.models import EntryClassification, PlaylistSnapshot, SourcePlaylistEntry
from symphonia.providers.contracts import ProviderPlaylistEntry
from symphonia.providers.importing import CollectionImportResult

from .sqlite_common import connect, initialize_with_cleanup


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class IncompleteCollectionError(ValueError):
    pass


class SnapshotConflictError(ValueError):
    """Raised when a snapshot ID is reused for different imported content."""


@dataclass(frozen=True, slots=True)
class StoredPlaylistSnapshot:
    snapshot_id: str
    provider: str
    namespace: str
    playlist_id: str
    revision: str | None
    published_at: datetime
    snapshot: PlaylistSnapshot


class PlaylistProjectionRepository:
    """Keep the last complete projection when a later import is incomplete."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = connect(path)
        initialize_with_cleanup(self._connection, self._migrate)

    def close(self) -> None:
        self._connection.close()

    def healthcheck(self) -> bool:
        """Return whether schema and projection references are readable."""

        try:
            integrity = self._connection.execute("PRAGMA integrity_check(1)").fetchone()
            if integrity is None or integrity[0] != "ok":
                return False
            if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                return False
        except sqlite3.Error:
            return False
        return True

    def _migrate(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS playlist_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                namespace TEXT NOT NULL,
                playlist_id TEXT NOT NULL,
                revision TEXT,
                published_at TEXT NOT NULL,
                UNIQUE (provider, namespace, playlist_id, snapshot_id)
            );
            CREATE TABLE IF NOT EXISTS playlist_snapshot_entries (
                snapshot_id TEXT NOT NULL REFERENCES playlist_snapshots(snapshot_id),
                occurrence_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                provider_track_id TEXT NOT NULL,
                provider_track_object_type TEXT NOT NULL DEFAULT 'track',
                provider_track_title TEXT,
                source_added_at TEXT,
                provider_track_namespace TEXT NOT NULL,
                media_kind TEXT NOT NULL,
                available INTEGER NOT NULL,
                PRIMARY KEY (snapshot_id, occurrence_id),
                UNIQUE (snapshot_id, position)
            );
            CREATE TABLE IF NOT EXISTS current_playlist_snapshots (
                provider TEXT NOT NULL,
                namespace TEXT NOT NULL,
                playlist_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL REFERENCES playlist_snapshots(snapshot_id),
                PRIMARY KEY (provider, namespace, playlist_id)
            );
            """
        )
        columns = {
            row[1]
            for row in self._connection.execute("PRAGMA table_info(playlist_snapshot_entries)").fetchall()
        }
        if "provider_track_object_type" not in columns:
            self._connection.execute(
                "ALTER TABLE playlist_snapshot_entries ADD COLUMN provider_track_object_type TEXT NOT NULL DEFAULT 'track'"
            )
        if "provider_track_title" not in columns:
            self._connection.execute("ALTER TABLE playlist_snapshot_entries ADD COLUMN provider_track_title TEXT")
        if "source_added_at" not in columns:
            self._connection.execute("ALTER TABLE playlist_snapshot_entries ADD COLUMN source_added_at TEXT")

    def publish(
        self,
        result: CollectionImportResult,
        *,
        snapshot_id: str,
        published_at: datetime,
    ) -> StoredPlaylistSnapshot:
        """Publish a complete result atomically; reject incomplete results."""

        if not result.complete:
            raise IncompleteCollectionError("incomplete collection cannot replace the current projection")
        if not snapshot_id.strip():
            raise ValueError("snapshot_id must not be empty")
        if not result.entries and result.playlist == "":
            raise ValueError("result must identify a playlist")
        existing = self._connection.execute(
            "SELECT * FROM playlist_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if existing is not None:
            if not self._matches_result(existing, result):
                raise SnapshotConflictError("snapshot_id is already bound to different imported content")
            # Publication is idempotent and must not move a newer current
            # pointer backwards if a client retries an older response.
            return self.get(snapshot_id)
        timestamp = _utc(published_at)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                """
                INSERT INTO playlist_snapshots (
                    snapshot_id, provider, namespace, playlist_id, revision, published_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (snapshot_id, result.provider, result.namespace, result.playlist, result.revision, timestamp),
            )
            self._connection.executemany(
                """
                INSERT INTO playlist_snapshot_entries (
                    snapshot_id, occurrence_id, position, provider_track_id,
                    provider_track_object_type, provider_track_title, source_added_at,
                    provider_track_namespace, media_kind, available
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_id,
                        entry.occurrence_id,
                        entry.position,
                        entry.track.object_id,
                        entry.track.object_type,
                        entry.title,
                        entry.source_added_at,
                        entry.track.namespace,
                        entry.media_kind.value,
                        int(entry.available),
                    )
                    for entry in result.entries
                ],
            )
            self._connection.execute(
                """
                INSERT INTO current_playlist_snapshots (provider, namespace, playlist_id, snapshot_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, namespace, playlist_id)
                DO UPDATE SET snapshot_id = excluded.snapshot_id
                """,
                (result.provider, result.namespace, result.playlist, snapshot_id),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get(snapshot_id)

    def _matches_result(self, snapshot_row: sqlite3.Row, result: CollectionImportResult) -> bool:
        if (
            snapshot_row["provider"] != result.provider
            or snapshot_row["namespace"] != result.namespace
            or snapshot_row["playlist_id"] != result.playlist
            or snapshot_row["revision"] != result.revision
        ):
            return False
        rows = self._connection.execute(
            """
            SELECT occurrence_id, position, provider_track_id,
                   provider_track_object_type, provider_track_title, source_added_at,
                   provider_track_namespace, media_kind, available
              FROM playlist_snapshot_entries
             WHERE snapshot_id = ?
             ORDER BY position
            """,
            (snapshot_row["snapshot_id"],),
        ).fetchall()
        entries = sorted(result.entries, key=lambda entry: entry.position)
        if len(rows) != len(entries):
            return False
        return all(
            row["occurrence_id"] == entry.occurrence_id
            and row["position"] == entry.position
            and row["provider_track_id"] == entry.track.object_id
            and row["provider_track_object_type"] == entry.track.object_type
            and row["provider_track_title"] == entry.title
            and row["source_added_at"] == entry.source_added_at
            and row["provider_track_namespace"] == entry.track.namespace
            and row["media_kind"] == entry.media_kind.value
            and bool(row["available"]) == entry.available
            for row, entry in zip(rows, entries)
        )

    def get(self, snapshot_id: str) -> StoredPlaylistSnapshot:
        row = self._connection.execute(
            "SELECT * FROM playlist_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        entries = self._entries(snapshot_id, row["provider"])
        return StoredPlaylistSnapshot(
            snapshot_id=row["snapshot_id"],
            provider=row["provider"],
            namespace=row["namespace"],
            playlist_id=row["playlist_id"],
            revision=row["revision"],
            published_at=_parse_utc(row["published_at"]),
            snapshot=PlaylistSnapshot(
                snapshot_id=row["snapshot_id"],
                source_provider=row["provider"],
                source_playlist_id=row["playlist_id"],
                entries=entries,
                source_namespace=row["namespace"],
            ),
        )

    def current(self, *, provider: str, namespace: str, playlist_id: str) -> StoredPlaylistSnapshot | None:
        row = self._connection.execute(
            """
            SELECT snapshot_id FROM current_playlist_snapshots
             WHERE provider = ? AND namespace = ? AND playlist_id = ?
            """,
            (provider, namespace, playlist_id),
        ).fetchone()
        return None if row is None else self.get(row["snapshot_id"])

    def summary(self) -> dict[str, Any]:
        """Return bounded import freshness/counts without playlist contents."""

        snapshots = self._connection.execute(
            "SELECT COUNT(*) AS count, MAX(published_at) AS latest_published_at FROM playlist_snapshots"
        ).fetchone()
        current = self._connection.execute(
            "SELECT COUNT(*) AS count FROM current_playlist_snapshots"
        ).fetchone()
        entries = self._connection.execute(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(CASE WHEN available = 0 THEN 1 ELSE 0 END), 0) AS unavailable_count
              FROM playlist_snapshot_entries
            """
        ).fetchone()
        return {
            "snapshot_count": int(snapshots["count"]),
            "current_playlist_count": int(current["count"]),
            "entry_count": int(entries["count"]),
            "unavailable_entry_count": int(entries["unavailable_count"]),
            "latest_published_at": snapshots["latest_published_at"],
        }

    def _entries(self, snapshot_id: str, provider: str) -> tuple[SourcePlaylistEntry, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM playlist_snapshot_entries
             WHERE snapshot_id = ? ORDER BY position
            """,
            (snapshot_id,),
        ).fetchall()
        return tuple(
            SourcePlaylistEntry(
                occurrence_id=row["occurrence_id"],
                position=row["position"],
                provider_track_id=row["provider_track_id"],
                provider_track_object_type=row["provider_track_object_type"],
                provider_track_title=row["provider_track_title"],
                source_added_at=row["source_added_at"],
                classification=EntryClassification.UNMATCHED if row["available"] else EntryClassification.UNAVAILABLE,
                reason=None if row["available"] else "provider reported item unavailable",
            )
            for row in rows
        )
