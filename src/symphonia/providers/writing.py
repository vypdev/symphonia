"""Normalized target-playlist write contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from .errors import redact_error_detail


class WriteOutcome(str, Enum):
    CONFIRMED_SUCCESS = "confirmed_success"
    RETRYABLE = "retryable"
    RATE_LIMITED = "rate_limited"
    UNKNOWN_OUTCOME = "unknown_outcome"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(frozen=True, slots=True)
class TargetPlaylist:
    provider_playlist_id: str

    def __post_init__(self) -> None:
        if not self.provider_playlist_id.strip():
            raise ValueError("provider_playlist_id must not be empty")


@dataclass(frozen=True, slots=True)
class WriteResult:
    outcome: WriteOutcome
    provider_code: str | None = None
    detail: str | None = None
    retry_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.detail is not None:
            object.__setattr__(self, "detail", redact_error_detail(self.detail))


class ProviderWriteError(RuntimeError):
    """A target-creation failure with an explicit retry/reconciliation class."""

    def __init__(
        self,
        outcome: WriteOutcome,
        detail: str,
        provider_code: str | None = None,
        retry_at: datetime | None = None,
    ) -> None:
        redacted_detail = redact_error_detail(detail)
        super().__init__(redacted_detail)
        self.outcome = outcome
        self.detail = redacted_detail
        self.provider_code = provider_code
        self.retry_at = retry_at


class PlaylistWriter(Protocol):
    """Port used by the copy executor; concrete providers stay outside it."""

    def ensure_target_playlist(
        self,
        *,
        provider: str,
        name: str,
        visibility: str,
        idempotency_key: str,
    ) -> TargetPlaylist: ...

    def add_entry(
        self,
        *,
        target_playlist_id: str,
        provider_track_id: str,
        idempotency_key: str,
    ) -> WriteResult: ...

    def reconcile_target_playlist(self, *, idempotency_key: str) -> TargetPlaylist | None: ...

    def reconcile_entry(
        self,
        *,
        target_playlist_id: str,
        provider_track_id: str,
        idempotency_key: str,
    ) -> bool: ...
