from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.validate_specs import _validate_markdown_links, _validate_requirements, validate


class SpecValidatorTests(unittest.TestCase):
    def test_repository_specifications_are_consistent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(validate(root), [])

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
