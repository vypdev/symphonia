"""Pure capability intersection and requirement checks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import Capability, ProviderCapabilities


class CapabilityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CapabilityLayers:
    adapter: ProviderCapabilities
    connection: ProviderCapabilities
    object: ProviderCapabilities | None = None
    health: ProviderCapabilities | None = None

    def effective(self) -> ProviderCapabilities:
        layers = [self.adapter, self.connection]
        if self.object is not None:
            layers.append(self.object)
        if self.health is not None:
            layers.append(self.health)
        enabled = set(layers[0].enabled)
        for layer in layers[1:]:
            enabled.intersection_update(layer.enabled)
        versions = "+".join(layer.evidence_version for layer in layers)
        observed_at = max(layer.observed_at for layer in layers)
        return ProviderCapabilities(frozenset(enabled), f"intersection:{versions}", observed_at)


def missing_capabilities(
    capabilities: ProviderCapabilities,
    required: Iterable[Capability],
) -> frozenset[Capability]:
    return frozenset(capability for capability in required if capability not in capabilities.enabled)


def require_capabilities(capabilities: ProviderCapabilities, required: Iterable[Capability]) -> None:
    missing = missing_capabilities(capabilities, required)
    if missing:
        names = ", ".join(sorted(capability.value for capability in missing))
        raise CapabilityError(f"required capabilities are unavailable: {names}")

