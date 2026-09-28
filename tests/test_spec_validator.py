from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.validate_specs import (
    _validate_catalog_shape,
    _validate_markdown_links,
    _validate_requirements,
    _validate_sdds,
    validate,
)


class SpecValidatorTests(unittest.TestCase):
    @staticmethod
    def _capability(status: str, blockers: list[str]) -> dict[str, object]:
        return {
            "id": "example",
            "title": "Example",
            "status": status,
            "scope": "Example scope",
            "owner": "Owner",
            "specification": "specs/example.md",
            "requirements": ["SYM-PLAY-001"],
            "evidence": [],
            "implementationEvidence": {"code": [], "tests": [], "documentation": []},
            "blockers": blockers,
        }

    def test_repository_specifications_are_consistent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(validate(root), [])

    def test_ready_sdd_cannot_keep_catalog_blockers(self) -> None:
        capability = self._capability(
            "ready-for-implementation", ["unproven broker pairing"]
        )
        errors: list[str] = []
        _validate_catalog_shape(
            Path("/unused"), {"version": 1, "capabilities": [capability]}, errors
        )
        self.assertIn(
            "catalog capability 0 cannot be ready-for-implementation while blockers remain",
            errors,
        )

    def test_implemented_sdd_needs_code_tests_and_documentation_evidence(self) -> None:
        capability = self._capability("implemented", [])
        errors: list[str] = []
        _validate_catalog_shape(
            Path("/unused"), {"version": 1, "capabilities": [capability]}, errors
        )
        for field in ("code", "tests", "documentation"):
            self.assertIn(
                f"catalog capability 0 implemented status requires implementationEvidence.{field}",
                errors,
            )

    def test_draft_can_retain_blockers_and_foundation_evidence(self) -> None:
        capability = self._capability("draft", ["live provider proof"])
        errors: list[str] = []
        _validate_catalog_shape(
            Path("/unused"), {"version": 1, "capabilities": [capability]}, errors
        )
        self.assertEqual(errors, [])

    def test_ready_sdd_with_no_blockers_is_structurally_valid(self) -> None:
        capability = self._capability("ready-for-implementation", [])
        errors: list[str] = []
        _validate_catalog_shape(
            Path("/unused"), {"version": 1, "capabilities": [capability]}, errors
        )
        self.assertEqual(errors, [])

    def test_implemented_sdd_with_complete_evidence_is_structurally_valid(self) -> None:
        capability = self._capability("implemented", [])
        capability["implementationEvidence"] = {
            "code": ["src/example.py"],
            "tests": ["tests/test_example.py"],
            "documentation": ["docs/example.md"],
        }
        errors: list[str] = []
        _validate_catalog_shape(
            Path("/unused"), {"version": 1, "capabilities": [capability]}, errors
        )
        self.assertEqual(errors, [])

    def test_malformed_catalog_arrays_are_reported_without_crashing(self) -> None:
        capability = self._capability("draft", [])
        capability["requirements"] = [{"not": "a requirement"}]
        capability["blockers"] = [{"not": "a blocker"}]
        errors: list[str] = []
        _validate_catalog_shape(
            Path("/unused"), {"version": 1, "capabilities": [capability]}, errors
        )
        self.assertIn(
            "catalog capability 0 requirements must be an array of unique non-empty strings",
            errors,
        )
        self.assertIn(
            "catalog capability 0 blockers must be an array of unique non-empty strings",
            errors,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            _validate_requirements(root, [capability], errors)
        self.assertEqual(len(errors), 2)

    def test_primary_sdd_must_declare_exactly_one_status(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            specs = root / "specs"
            specs.mkdir()
            (specs / "example.md").write_text(
                "- Catalog capability ID: `example`\n", encoding="utf-8"
            )
            errors: list[str] = []
            _validate_sdds(root, [self._capability("draft", [])], errors)
            self.assertEqual(errors, ["specs/example.md must declare exactly one status"])

    def test_generated_dependency_markdown_is_not_treated_as_ours(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "guide.md").write_text("[missing](missing.md)", encoding="utf-8")
            vendor = docs / "node_modules" / "package"
            vendor.mkdir(parents=True)
            (vendor / "README.md").write_text("[also missing](elsewhere.md) SYM-UI-999", encoding="utf-8")

            errors: list[str] = []
            _validate_markdown_links(root, errors)
            self.assertEqual(errors, ["docs/guide.md links to missing path: missing.md"])

            errors = []
            _validate_requirements(root, [{"id": "ui", "requirements": ["SYM-UI-999"]}], errors)
            self.assertEqual(errors, ["ui references unknown requirement SYM-UI-999"])


if __name__ == "__main__":
    unittest.main()
