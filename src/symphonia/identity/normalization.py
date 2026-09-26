"""Deterministic, lossless comparison-field normalization.

Normalization is intentionally not matching. It produces reviewable derived
fields while retaining every original value and does not decide whether two
provider representations are the same recording.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w]+", re.UNICODE)
_ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")
_VERSION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("live", re.compile(r"\blive\b", re.IGNORECASE)),
    ("acoustic", re.compile(r"\bacoustic\b", re.IGNORECASE)),
    ("remix", re.compile(r"\bremix(?:ed)?\b", re.IGNORECASE)),
    ("remaster", re.compile(r"\b(?:digital\s+)?remaster(?:ed)?\b", re.IGNORECASE)),
    ("edit", re.compile(r"\b(?:radio|single|extended)\s+edit\b|\bedit\b", re.IGNORECASE)),
    ("demo", re.compile(r"\bdemo\b", re.IGNORECASE)),
    ("instrumental", re.compile(r"\binstrumental\b", re.IGNORECASE)),
    ("karaoke", re.compile(r"\bk karaoke\b|\bkaraoke\b", re.IGNORECASE)),
    ("clean", re.compile(r"\bclean\b", re.IGNORECASE)),
    ("explicit", re.compile(r"\bexplicit\b", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class NormalizedRecordingMetadata:
    """Original and derived fields used by a future resolver policy."""

    original_title: str
    normalized_title: str
    original_artists: tuple[str, ...]
    normalized_artists: tuple[str, ...]
    version_tokens: tuple[str, ...]
    original_isrc: str | None = None
    normalized_isrc: str | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.original_title.strip():
            raise ValueError("original_title must not be empty")
        if not self.normalized_title.strip():
            raise ValueError("normalized_title must not be empty")
        if len(self.original_artists) != len(self.normalized_artists):
            raise ValueError("original and normalized artist fields must have equal length")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        if self.normalized_isrc is not None and not _ISRC.fullmatch(self.normalized_isrc):
            raise ValueError("normalized_isrc is not a valid ISRC")


def normalize_text(value: str) -> str:
    """Return a Unicode-safe comparison form without changing stored input."""

    if not isinstance(value, str):
        raise TypeError("text to normalize must be a string")
    folded = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = _PUNCTUATION.sub(" ", folded)
    return _WHITESPACE.sub(" ", without_punctuation).strip()


def normalize_isrc(value: str | None) -> str | None:
    """Normalize a candidate ISRC, returning ``None`` for malformed input."""

    if value is None:
        return None
    compact = re.sub(r"[\s-]+", "", value).upper()
    return compact if _ISRC.fullmatch(compact) else None


def version_tokens(title: str) -> tuple[str, ...]:
    """Extract known version markers in stable policy order."""

    if not isinstance(title, str):
        raise TypeError("title must be a string")
    return tuple(name for name, pattern in _VERSION_PATTERNS if pattern.search(title))


def normalize_recording_metadata(
    *,
    title: str,
    artists: tuple[str, ...] | list[str],
    isrc: str | None = None,
    duration_ms: int | None = None,
) -> NormalizedRecordingMetadata:
    """Build comparison fields while keeping provider values intact."""

    original_artists = tuple(artists)
    if not original_artists or any(not artist.strip() for artist in original_artists):
        raise ValueError("artists must contain at least one nonblank value")
    normalized_isrc = normalize_isrc(isrc)
    return NormalizedRecordingMetadata(
        original_title=title,
        normalized_title=normalize_text(title),
        original_artists=original_artists,
        normalized_artists=tuple(normalize_text(artist) for artist in original_artists),
        version_tokens=version_tokens(title),
        original_isrc=isrc,
        normalized_isrc=normalized_isrc,
        duration_ms=duration_ms,
    )


__all__ = [
    "NormalizedRecordingMetadata",
    "normalize_isrc",
    "normalize_recording_metadata",
    "normalize_text",
    "version_tokens",
]
