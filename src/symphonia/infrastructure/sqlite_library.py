"""Atomic persistence for complete imported playlist snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3

from symphonia.domain.models import EntryClassification, PlaylistSnapshot, SourcePlaylistEntry
from symphonia.providers.contracts import ProviderPlaylistEntry
from symphonia.providers.importing import CollectionImportResult


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class IncompleteCollectionError(ValueError):
    pass


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
        self._connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self._connection.close()

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
                    provider_track_namespace, media_kind, available
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_id,
                        entry.occurrence_id,
                        entry.position,
                        entry.track.object_id,
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
                classification=EntryClassification.UNMATCHED if row["available"] else EntryClassification.UNAVAILABLE,
                reason=None if row["available"] else "provider reported item unavailable",
            )
            for row in rows
        )

