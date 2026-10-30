"""Consumer regressions against the original Copilot validator, not a new schema."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest

from tools.validate_specs import VALIDATOR, validate


ROOT = Path(__file__).resolve().parents[1]


class SpecValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in ("specs/example.md", "source/entry.py", "checks/example.py", "docs/guide.md"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        self.capability = {
            "id": "example", "title": "Example", "status": "proposed",
            "scope": "Proposed capability with bounded research evidence", "owner": "Maintainers",
            "lastVerified": "2026-10-29", "specs": ["specs/example.md"], "workflows": [],
            "entrypoints": ["source/entry.py"], "code": ["source/entry.py"],
            "tests": ["checks/example.py"], "documentation": ["docs/guide.md"],
        }
        self.catalog = {"version": 1, "capabilities": [self.capability]}
        self.write_catalog()
        self.generate()

    def write_catalog(self) -> None:
        (self.root / "specs/catalog.json").write_text(json.dumps(self.catalog))

    def generate(self) -> None:
        subprocess.run(
            ["node", "-e", "require(process.argv[1]).main(['--write'], process.argv[2])",
             str(VALIDATOR), str(self.root)], check=True, capture_output=True, text=True,
        )

    def test_repository_passes_original_copilot_validator(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_current_generated_catalog_links_resolve(self) -> None:
        # Exercise the actual consumer inventory, without modifying SDK policy.
        index = ROOT / "specs/CATALOG.md"
        targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", index.read_text())
        self.assertGreater(len(targets), 50)
        for target in targets:
            with self.subTest(target=target):
                self.assertTrue((index.parent / target).is_file(), target)

    def test_proposed_research_and_language_neutral_paths_are_supported(self) -> None:
        self.assertEqual(validate(self.root), [])

    def test_previous_native_status_and_fields_cannot_replace_sdk_contract(self) -> None:
        self.capability["status"] = "draft"
        self.capability["specification"] = self.capability.pop("specs")[0]
        self.write_catalog()
        errors = "\n".join(validate(self.root))
        self.assertIn(".status must be one of", errors)
        self.assertIn(".specs must be an array", errors)

    def test_missing_evidence_is_rejected_even_for_proposed_capabilities(self) -> None:
        for field in ("entrypoints", "code", "tests", "documentation"):
            with self.subTest(field=field):
                original = self.capability[field]
                self.capability[field] = []
                self.write_catalog()
                self.assertIn(f".{field} must not be empty", "\n".join(validate(self.root)))
                self.capability[field] = original

    def test_duplicate_capability_and_sdd_ownership_are_rejected(self) -> None:
        self.catalog["capabilities"].append(dict(self.capability))
        self.write_catalog()
        errors = "\n".join(validate(self.root))
        self.assertIn(".id duplicates example", errors)
        self.assertIn("registered by multiple capabilities", errors)

    def test_unregistered_product_specification_is_rejected(self) -> None:
        (self.root / "specs/orphan.md").write_text("orphan")
        self.assertIn("not registered", "\n".join(validate(self.root)))

    def test_catalog_generation_and_stale_index_detection(self) -> None:
        self.capability["scope"] = "Changed source-backed scope"
        self.write_catalog()
        self.assertIn("CATALOG.md is stale", "\n".join(validate(self.root)))
        self.generate()
        self.assertEqual(validate(self.root), [])
        self.assertIn("Changed source-backed scope", (self.root / "specs/CATALOG.md").read_text())

    def test_nested_primary_spec_links_resolve_in_table_and_evidence(self) -> None:
        nested = self.root / "specs/nested/example.md"
        nested.parent.mkdir()
        (self.root / "specs/example.md").rename(nested)
        self.capability["specs"] = ["specs/nested/example.md"]
        self.write_catalog()
        self.generate()
        self.assertEqual(validate(self.root), [])
        index = (self.root / "specs/CATALOG.md").read_text()
        self.assertIn("[Example](./nested/example.md)", index)
        self.assertIn("[`specs/nested/example.md`](./nested/example.md)", index)

    def test_companion_and_evidence_keep_subdirectories_with_same_basename(self) -> None:
        nested = self.root / "specs/companion/example.md"
        nested.parent.mkdir()
        nested.write_text("Companion fixture\n")
        self.capability["specs"].append("specs/companion/example.md")
        self.capability["documentation"].append("specs/companion/example.md")
        self.write_catalog()
        self.generate()
        self.assertEqual(validate(self.root), [])
        index = (self.root / "specs/CATALOG.md").read_text()
        self.assertIn("[Example](./example.md) + 1 companion", index)
        self.assertEqual(index.count("[`specs/companion/example.md`](./companion/example.md)"), 2)

    def test_missing_and_escaping_evidence_are_rejected(self) -> None:
        for path in ("source/missing.py", "../outside.py", "/outside.py"):
            with self.subTest(path=path):
                self.capability["code"] = [path]
                self.write_catalog()
                self.assertTrue(validate(self.root))

    def test_symlinked_evidence_is_rejected(self) -> None:
        (self.root / "source/alias.py").symlink_to(self.root / "source/entry.py")
        self.capability["code"] = ["source/alias.py"]
        self.write_catalog()
        self.assertIn("without symlinks", "\n".join(validate(self.root)))

    def test_generation_does_not_overwrite_a_symlink_target(self) -> None:
        with TemporaryDirectory() as directory:
            outside = Path(directory) / "sentinel.md"
            outside.write_text("Retain this unrelated content.\n")
            index = self.root / "specs/CATALOG.md"
            index.unlink()
            index.symlink_to(outside)
            result = subprocess.run(
                ["node", "-e", "require(process.argv[1]).main(['--write'], process.argv[2])",
                 str(VALIDATOR), str(self.root)], capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without symlinks", result.stderr)
            self.assertEqual(outside.read_text(), "Retain this unrelated content.\n")

    def test_generation_does_not_follow_a_dangling_output_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            outside = Path(directory) / "not-created.md"
            index = self.root / "specs/CATALOG.md"
            index.unlink()
            index.symlink_to(outside)
            result = subprocess.run(
                ["node", "-e", "require(process.argv[1]).main(['--write'], process.argv[2])",
                 str(VALIDATOR), str(self.root)], capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without symlinks", result.stderr)
            self.assertFalse(outside.exists())

    def test_invalid_verification_date_is_rejected(self) -> None:
        self.capability["lastVerified"] = "2026-02-30"
        self.write_catalog()
        self.assertIn("lastVerified must use YYYY-MM-DD", "\n".join(validate(self.root)))

    def test_as_built_claim_requires_original_baseline_contract(self) -> None:
        self.capability["status"] = "as-built-baseline"
        self.write_catalog()
        self.assertIn("retrospective classification", "\n".join(validate(self.root)))

    def test_copilot_sources_match_provenance_with_only_declared_rendering_patch(self) -> None:
        manifest = json.loads((ROOT / "tools/copilot-specifications/provenance.json").read_text())
        for entry in manifest["files"]:
            with self.subTest(path=entry["path"]):
                content = (ROOT / entry["path"]).read_bytes()
                if "localPatch" in entry:
                    blob = b"blob " + str(len(content)).encode() + b"\0" + content
                    self.assertEqual(hashlib.sha1(blob).hexdigest(), entry["localGitBlobSha"])
                    source = content.decode()
                    for replacement in entry["localPatch"]["replacements"]:
                        self.assertEqual(source.count(replacement["after"]), replacement["occurrences"])
                        source = source.replace(replacement["after"], replacement["before"])
                    content = source.encode()
                blob = b"blob " + str(len(content)).encode() + b"\0" + content
                self.assertEqual(hashlib.sha1(blob).hexdigest(), entry["gitBlobSha"])


if __name__ == "__main__":
    unittest.main()
