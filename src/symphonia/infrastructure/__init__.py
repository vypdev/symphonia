"""Infrastructure adapters for the Symphonia core."""

from .sqlite_operations import (
    IdempotencyConflict,
    OperationNotFound,
    OperationEvent,
    OperationRepository,
    LeaseConflict,
)
from .sqlite_plans import CopyPlanNotFound, CopyPlanRepository, StoredCopyPlan
from .sqlite_resolutions import ResolutionDecisionRepository
from .sqlite_library import IncompleteCollectionError, PlaylistProjectionRepository, StoredPlaylistSnapshot

__all__ = [
    "CopyPlanNotFound",
    "CopyPlanRepository",
    "IncompleteCollectionError",
    "IdempotencyConflict",
    "LeaseConflict",
    "OperationNotFound",
    "OperationEvent",
    "OperationRepository",
    "PlaylistProjectionRepository",
    "ResolutionDecisionRepository",
    "StoredCopyPlan",
    "StoredPlaylistSnapshot",
]
