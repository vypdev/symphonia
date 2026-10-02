"""Provider-independent published playlist projection values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import PlaylistSnapshot


@dataclass(frozen=True, slots=True)
class PublishedPlaylistSnapshot:
    snapshot_id: str
    provider: str
    namespace: str
    playlist_id: str
    revision: str | None
    published_at: datetime
    snapshot: PlaylistSnapshot
