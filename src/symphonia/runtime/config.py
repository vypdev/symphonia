"""Validated process configuration for the local and Home Assistant runtimes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
import unicodedata


def _has_control_characters(value: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in value)


def normalize_ingress_path(value: object) -> str:
    if not isinstance(value, str) or not value or not value.startswith("/"):
        raise ValueError("ingress path must start with '/'")
    if _has_control_characters(value):
        raise ValueError("ingress path must not contain control characters")
    if "?" in value or "#" in value:
        raise ValueError("ingress path must contain only a path")
    if "\\" in value or "//" in value:
        raise ValueError("ingress path contains an unsafe separator")
    normalized = value.rstrip("/") or "/"
    if any(segment in {".", ".."} for segment in normalized.split("/")):
        raise ValueError("ingress path contains an unsafe segment")
    return normalized


def _parse_port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
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


def normalize_database_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("database_path must not be empty")
    if _has_control_characters(value):
        raise ValueError("database_path must not contain control characters")
    return os.path.expanduser(value.strip())


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
        if _has_control_characters(self.host):
            raise ValueError("host must not contain control characters")
        host = self.host.strip()
        if not host or any(char.isspace() for char in host):
            raise ValueError("host must be a non-empty value without whitespace")
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", _parse_port(self.port))
        object.__setattr__(self, "database_path", normalize_database_path(self.database_path))
        object.__setattr__(self, "ingress_path", normalize_ingress_path(self.ingress_path))

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "RuntimeConfig":
        values = os.environ if environ is None else environ
        return cls(
            host=values.get("SYMPHONIA_HOST", "127.0.0.1"),
            port=_parse_port(values.get("SYMPHONIA_PORT", "8099")),
            database_path=values.get("SYMPHONIA_DATABASE", "./symphonia.sqlite3"),
            ingress_path=values.get("SYMPHONIA_INGRESS_PATH", "/"),
        )


__all__ = ["RuntimeConfig", "normalize_database_path", "normalize_ingress_path"]
