"""Provider adapter registry used by the composition root."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ProviderAdapter, ProviderManifest


class ProviderAlreadyRegistered(ValueError):
    pass


class ProviderNotRegistered(LookupError):
    pass


@dataclass(slots=True)
class ProviderRegistry:
    """Keep provider discovery explicit and deterministic."""

    _adapters: dict[str, ProviderAdapter]

    def __init__(self) -> None:
        self._adapters = {}

    def register(self, adapter: ProviderAdapter) -> None:
        manifest = adapter.manifest
        provider = manifest.provider.strip()
        if not provider:
            raise ValueError("provider manifest must identify a provider")
        if provider in self._adapters:
            raise ProviderAlreadyRegistered(provider)
        self._adapters[provider] = adapter

    def get(self, provider: str) -> ProviderAdapter:
        try:
            return self._adapters[provider]
        except KeyError as error:
            raise ProviderNotRegistered(provider) from error

    def manifests(self) -> tuple[ProviderManifest, ...]:
        return tuple(self._adapters[key].manifest for key in sorted(self._adapters))

