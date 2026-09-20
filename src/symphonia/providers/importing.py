"""Pure import collection and provider-to-domain snapshot conversion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from symphonia.domain.models import EntryClassification, PlaylistSnapshot, SourcePlaylistEntry

from .contracts import ProviderPlaylistEntry, ProviderPlaylistPage


class ImportIssue(str, Enum):
    NO_PAGES = "no_pages"
    MISSING_CONTINUATION = "missing_continuation"
    REPEATED_CURSOR = "repeated_cursor"
    CONFLICTING_OCCURRENCE = "conflicting_occurrence"
    DUPLICATE_OCCURRENCE = "duplicate_occurrence"
    INCONSISTENT_PLAYLIST = "inconsistent_playlist"


@dataclass(frozen=True, slots=True)
class CollectionImportResult:
    playlist: str
    provider: str
    entries: tuple[ProviderPlaylistEntry, ...]
    complete: bool
    issues: tuple[ImportIssue, ...]
    revision: str | None


def collect_playlist_pages(pages: list[ProviderPlaylistPage] | tuple[ProviderPlaylistPage, ...]) -> CollectionImportResult:
    """Collect pages without silently truncating or collapsing occurrences.

    Exact repeated occurrences caused by an overlapping page are de-duplicated
    by occurrence ID and recorded as an issue. A conflicting repeat, repeated
    cursor, missing continuation, or mixed playlist makes the result incomplete.
    """

    if not pages:
        return CollectionImportResult("", "", (), False, (ImportIssue.NO_PAGES,), None)

    first = pages[0].playlist
    issues: list[ImportIssue] = []
    entries_by_id: dict[str, ProviderPlaylistEntry] = {}
    seen_cursors: set[str] = set()
    seen_next_cursors: set[str] = set()
    complete = True
    for index, page in enumerate(pages):
        if page.playlist.external_key != first.external_key:
            issues.append(ImportIssue.INCONSISTENT_PLAYLIST)
            complete = False
        if page.cursor is not None and page.cursor in seen_cursors:
            issues.append(ImportIssue.REPEATED_CURSOR)
            complete = False
        if page.cursor is not None:
            seen_cursors.add(page.cursor)
        if page.next_cursor is not None and page.next_cursor in seen_next_cursors:
            issues.append(ImportIssue.REPEATED_CURSOR)
            complete = False
        if page.next_cursor is not None:
            seen_next_cursors.add(page.next_cursor)

        for entry in page.entries:
            previous = entries_by_id.get(entry.occurrence_id)
            if previous is None:
                entries_by_id[entry.occurrence_id] = entry
            elif previous == entry:
                issues.append(ImportIssue.DUPLICATE_OCCURRENCE)
            else:
                issues.append(ImportIssue.CONFLICTING_OCCURRENCE)
                complete = False

        if index < len(pages) - 1 and page.next_cursor is None:
            issues.append(ImportIssue.MISSING_CONTINUATION)
            complete = False
        if index == len(pages) - 1:
            if not page.complete or page.next_cursor is not None:
                complete = False
                if not page.complete:
                    issues.append(ImportIssue.MISSING_CONTINUATION)

    ordered = tuple(sorted(entries_by_id.values(), key=lambda entry: entry.position))
    return CollectionImportResult(
        playlist=first.object_id,
        provider=first.provider,
        entries=ordered,
        complete=complete and not any(issue in {ImportIssue.CONFLICTING_OCCURRENCE, ImportIssue.REPEATED_CURSOR} for issue in issues),
        issues=tuple(dict.fromkeys(issues)),
        revision=pages[-1].revision,
    )


def to_playlist_snapshot(result: CollectionImportResult, snapshot_id: str) -> PlaylistSnapshot:
    """Convert a collected provider result into copy-planner input.

    Import does not perform identity resolution. Available entries therefore
    start as ``unmatched``; unavailable entries remain explicit and visible.
    """

    entries = tuple(
        SourcePlaylistEntry(
            occurrence_id=entry.occurrence_id,
            position=entry.position,
            provider_track_id=entry.track.object_id,
            classification=EntryClassification.UNMATCHED if entry.available else EntryClassification.UNAVAILABLE,
            reason=None if entry.available else "provider reported item unavailable",
        )
        for entry in result.entries
    )
    return PlaylistSnapshot(
        snapshot_id=snapshot_id,
        source_provider=result.provider,
        source_playlist_id=result.playlist,
        entries=entries,
    )
