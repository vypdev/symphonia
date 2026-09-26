from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src" / "symphonia"


def _absolute_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append(node.module)
    return imports


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_does_not_import_adapters_or_host_frameworks(self) -> None:
        forbidden_prefixes = (
            "symphonia.infrastructure",
            "symphonia.providers",
            "symphonia.runtime",
            "homeassistant",
            "supervisor",
            "aiohttp",
            "fastapi",
            "flask",
            "starlette",
        )
        violations = []
        for path in sorted((SOURCE_ROOT / "domain").glob("*.py")):
            for module in _absolute_imports(path):
                if module.startswith(forbidden_prefixes):
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
        self.assertEqual(violations, [])

    def test_foundation_source_uses_only_stdlib_and_local_modules(self) -> None:
        stdlib = set(sys.stdlib_module_names)
        violations = []
        for path in sorted(SOURCE_ROOT.rglob("*.py")):
            for module in _absolute_imports(path):
                root = module.split(".", 1)[0]
                if root not in stdlib and root != "symphonia":
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
