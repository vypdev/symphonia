"""SQLite persistence for provider connections and effective capabilities."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from symphonia.providers.connections import ConnectionState, ProviderConnection
from symphonia.providers.contracts import Capability, ProviderCapabilities

from .sqlite_common import connect


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class ConnectionNotFound(LookupError):
    pass


class ConnectionConflict(ValueError):
    pass


class ProviderConnectionRepository:
    """Persist account identity and capability evidence, never secret contents."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = connect(path)
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def healthcheck(self) -> bool:
        """Return whether the migrated connection store can be read."""

        try:
            row = self._connection.execute("SELECT 1 AS healthy").fetchone()
        except sqlite3.Error:
            return False
        return row is not None and row["healthy"] == 1

    def _migrate(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS provider_connections (
                connection_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_account_id TEXT NOT NULL,
                state TEXT NOT NULL,
                manifest_version TEXT NOT NULL,
                secret_ref TEXT,
                capabilities_json TEXT,
                expires_at TEXT,
                health_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (provider, provider_account_id)
            );
            CREATE INDEX IF NOT EXISTS provider_connections_state_idx
                ON provider_connections (state, provider, updated_at);
            """
        )

    def create(self, connection: ProviderConnection) -> ProviderConnection:
        """Create a connection once; repeated identical creates are idempotent."""

        payload = _serialize_capabilities(connection.capabilities)
        try:
            self._connection.execute(
                """
                INSERT INTO provider_connections (
                    connection_id, provider, provider_account_id, state, manifest_version,
                    secret_ref, capabilities_json, expires_at, health_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    connection.connection_id,
                    connection.provider,
                    connection.provider_account_id,
                    connection.state.value,
                    connection.manifest_version,
                    connection.secret_ref,
                    payload,
                    None if connection.expires_at is None else _utc(connection.expires_at),
                    connection.health_code,
                    _utc(connection.created_at),
                    _utc(connection.updated_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            row = self._connection.execute(
                "SELECT * FROM provider_connections WHERE connection_id = ?",
                (connection.connection_id,),
            ).fetchone()
            if row is None:
                raise ConnectionConflict("provider account is already connected") from error
            existing = self._record(row)
            if existing != connection:
                raise ConnectionConflict("provider account is already connected") from error
            return existing
        return self.get(connection.connection_id)

    def get(self, connection_id: str) -> ProviderConnection:
        row = self._connection.execute(
            "SELECT * FROM provider_connections WHERE connection_id = ?", (connection_id,)
        ).fetchone()
        if row is None:
            raise ConnectionNotFound(connection_id)
        return self._record(row)

    def list(self, *, provider: str | None = None) -> tuple[ProviderConnection, ...]:
        if provider is None:
            rows = self._connection.execute(
                "SELECT * FROM provider_connections ORDER BY provider, created_at, connection_id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT * FROM provider_connections
                 WHERE provider = ?
                 ORDER BY created_at, connection_id
                """,
                (provider,),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def health_summary(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Return provider/state counts without account or credential data."""

        rows = self._connection.execute(
            """
            SELECT provider, state, COUNT(*) AS count
              FROM provider_connections
             GROUP BY provider, state
             ORDER BY provider, state
            """
        ).fetchall()
        by_provider: dict[str, dict[str, int]] = {}
        total = 0
        for row in rows:
            provider = str(row["provider"])
            count = int(row["count"])
            by_provider.setdefault(provider, {})[str(row["state"])] = count
            total += count
        summary: dict[str, Any] = {"total": total, "by_provider": by_provider}
        if now is not None:
            expired = self._connection.execute(
                """
                SELECT COUNT(*) AS count
                  FROM provider_connections
                 WHERE state != 'disconnected'
                   AND expires_at IS NOT NULL
                   AND expires_at <= ?
                """,
                (_utc(now),),
            ).fetchone()
            summary["expired_count"] = int(expired["count"])
        return summary

    def record_probe(
        self,
        connection_id: str,
        *,
        state: ConnectionState,
        capabilities: ProviderCapabilities | None,
        health_code: str | None,
        expires_at: datetime | None,
        now: datetime,
    ) -> ProviderConnection:
        """Atomically publish the latest safe capability/health observation."""

        current = self.get(connection_id)
        if state is not ConnectionState.DISCONNECTED and not current.secret_ref:
            raise ConnectionConflict("cannot activate a connection without its secret reference")
        self._connection.execute(
            """
            UPDATE provider_connections
               SET state = ?, capabilities_json = ?, expires_at = ?, health_code = ?, updated_at = ?
             WHERE connection_id = ?
            """,
            (
                state.value,
                _serialize_capabilities(capabilities),
                None if expires_at is None else _utc(expires_at),
                health_code,
                _utc(now),
                connection_id,
            ),
        )
        return self.get(connection_id)

    def disconnect(self, connection_id: str, *, now: datetime) -> ProviderConnection:
        """Fence future use and remove the local secret reference."""

        self.get(connection_id)
        self._connection.execute(
            """
            UPDATE provider_connections
               SET state = 'disconnected', secret_ref = NULL, capabilities_json = NULL,
                   expires_at = NULL, health_code = 'disconnected', updated_at = ?
             WHERE connection_id = ?
            """,
            (_utc(now), connection_id),
        )
        return self.get(connection_id)

    @staticmethod
    def _record(row: sqlite3.Row) -> ProviderConnection:
        return ProviderConnection(
            connection_id=row["connection_id"],
            provider=row["provider"],
            provider_account_id=row["provider_account_id"],
            state=ConnectionState(row["state"]),
            manifest_version=row["manifest_version"],
            secret_ref=row["secret_ref"],
            capabilities=_deserialize_capabilities(row["capabilities_json"]),
            created_at=_parse_utc(row["created_at"]),
            updated_at=_parse_utc(row["updated_at"]),
            expires_at=None if row["expires_at"] is None else _parse_utc(row["expires_at"]),
            health_code=row["health_code"],
        )


def _serialize_capabilities(capabilities: ProviderCapabilities | None) -> str | None:
    if capabilities is None:
        return None
    return json.dumps(
        {
            "enabled": sorted(capability.value for capability in capabilities.enabled),
            "evidence_version": capabilities.evidence_version,
            "observed_at": capabilities.observed_at,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _deserialize_capabilities(payload: str | None) -> ProviderCapabilities | None:
    if payload is None:
        return None
    value = json.loads(payload)
    return ProviderCapabilities(
        enabled=frozenset(Capability(item) for item in value["enabled"]),
        evidence_version=value["evidence_version"],
        observed_at=value["observed_at"],
    )
