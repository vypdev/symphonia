"""Validated process configuration for the local and Home Assistant runtimes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from collections.abc import Mapping


def _normalize_ingress_path(value: str) -> str:
    if not isinstance(value, str) or not value or not value.startswith("/"):
        raise ValueError("ingress path must start with '/'")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError("ingress path must not contain control characters")
    if "?" in value or "#" in value:
        raise ValueError("ingress path must contain only a path")
    normalized = value.rstrip("/") or "/"
    if "//" in normalized or "/.." in normalized or "/./" in normalized:
        raise ValueError("ingress path contains an unsafe segment")
    return normalized


def _parse_port(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("port must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("port must be an integer")
    try:
        port = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError("port must be an integer") from error
    if not 1 <= port <= 65_535:
        raise ValueError("port must be between 1 and 65535")
    return port


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Configuration that is safe to hand to the runtime composition root."""

    host: str = "127.0.0.1"
    port: int = 8099
    database_path: str = "./symphonia.sqlite3"
    ingress_path: str = "/"

    def __post_init__(self) -> None:
        if not isinstance(self.host, str):
            raise ValueError("host must be a non-empty value without whitespace")
        host = self.host.strip()
        if not host or any(char.isspace() for char in host):
            raise ValueError("host must be a non-empty value without whitespace")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in host):
            raise ValueError("host must not contain control characters")
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", _parse_port(self.port))
        if not isinstance(self.database_path, str) or not self.database_path.strip():
            raise ValueError("database_path must not be empty")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in self.database_path):
            raise ValueError("database_path must not contain control characters")
        object.__setattr__(self, "database_path", self.database_path.strip())
        object.__setattr__(self, "ingress_path", _normalize_ingress_path(self.ingress_path))

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "RuntimeConfig":
        values = os.environ if environ is None else environ
        return cls(
            host=values.get("SYMPHONIA_HOST", "127.0.0.1"),
            port=_parse_port(values.get("SYMPHONIA_PORT", "8099")),
            database_path=values.get("SYMPHONIA_DATABASE", "./symphonia.sqlite3"),
            ingress_path=values.get("SYMPHONIA_INGRESS_PATH", "/"),
        )


__all__ = ["RuntimeConfig"]
