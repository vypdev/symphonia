from __future__ import annotations

import unittest

from symphonia.providers import (
    Capability,
    CapabilityError,
    CapabilityLayers,
    ProviderCapabilities,
    missing_capabilities,
    require_capabilities,
)


def capabilities(enabled: set[Capability], version: str) -> ProviderCapabilities:
    return ProviderCapabilities(frozenset(enabled), version, version)


class CapabilityTests(unittest.TestCase):
    def test_effective_capabilities_intersect_all_layers(self) -> None:
        effective = CapabilityLayers(
            adapter=capabilities({Capability.READ_PLAYLISTS, Capability.CREATE_PLAYLIST}, "adapter"),
            connection=capabilities({Capability.READ_PLAYLISTS, Capability.CREATE_PLAYLIST}, "connection"),
            object=capabilities({Capability.READ_PLAYLISTS}, "object"),
            health=capabilities({Capability.READ_PLAYLISTS}, "health"),
        ).effective()
        self.assertEqual(effective.enabled, frozenset({Capability.READ_PLAYLISTS}))
        self.assertEqual(effective.evidence_version, "intersection:adapter+connection+object+health")

    def test_requirement_check_reports_missing_capabilities(self) -> None:
        current = capabilities({Capability.READ_PLAYLISTS}, "probe")
        self.assertEqual(
            missing_capabilities(current, {Capability.READ_PLAYLISTS, Capability.CREATE_PLAYLIST}),
            frozenset({Capability.CREATE_PLAYLIST}),
        )
        with self.assertRaises(CapabilityError):
            require_capabilities(current, {Capability.CREATE_PLAYLIST})


if __name__ == "__main__":
    unittest.main()
