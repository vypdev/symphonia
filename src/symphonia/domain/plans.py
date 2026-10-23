"""Durable, provider-independent copy-plan state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import CopyPlan


@dataclass(frozen=True, slots=True)
class CopyPlanRecord:
    plan: CopyPlan
    accepted_at: datetime | None
