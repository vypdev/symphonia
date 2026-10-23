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
from .sqlite_library import (
    IncompleteCollectionError,
    PlaylistProjectionRepository,
    SnapshotConflictError,
    StoredPlaylistSnapshot,
)
from .sqlite_connections import (
    ConnectionConflict,
    ConnectionNotFound,
    ProviderConnectionRepository,
)
from .sqlite_authorization import (
    AuthorizationAttemptError,
    AuthorizationAttemptNotFound,
    AuthorizationAttemptRepository,
    state_digest,
)

__all__ = [
    "CopyPlanNotFound",
    "CopyPlanRepository",
    "IncompleteCollectionError",
    "ConnectionConflict",
    "ConnectionNotFound",
    "AuthorizationAttemptError",
    "AuthorizationAttemptNotFound",
    "AuthorizationAttemptRepository",
    "IdempotencyConflict",
    "LeaseConflict",
    "OperationNotFound",
    "OperationEvent",
    "OperationRepository",
    "PlaylistProjectionRepository",
    "ProviderConnectionRepository",
    "ResolutionDecisionRepository",
    "SnapshotConflictError",
    "StoredCopyPlan",
    "StoredPlaylistSnapshot",
    "state_digest",
]
