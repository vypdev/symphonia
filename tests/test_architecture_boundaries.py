from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src" / "symphonia"


def _resolved_imports(tree: ast.AST, package: str) -> list[str]:
    package_parts = package.split(".")
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package_parts):
                    raise ValueError("relative import escapes the package")
                base_parts = package_parts[: len(package_parts) - node.level + 1]
                if node.module:
                    base_parts.extend(node.module.split("."))
                base = ".".join(base_parts)
            else:
                base = node.module or ""
            if base:
                imports.append(base)
                imports.extend(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return imports


def _absolute_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative_parts = path.relative_to(SOURCE_ROOT).with_suffix("").parts
    package_parts = ("symphonia", *relative_parts[:-1])
    return _resolved_imports(tree, ".".join(package_parts))


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_relative_and_package_imports_are_resolved_before_checking_boundaries(self) -> None:
        imports = _resolved_imports(
            ast.parse(
                "from ..infrastructure import sqlite_operations\n"
                "from .. import runtime\n"
                "from symphonia import providers\n"
            ),
            "symphonia.domain",
        )
        self.assertIn("symphonia.infrastructure", imports)
        self.assertIn("symphonia.infrastructure.sqlite_operations", imports)
        self.assertIn("symphonia.runtime", imports)
        self.assertIn("symphonia.providers", imports)

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

    def test_provider_and_identity_layers_do_not_import_outer_layers(self) -> None:
        forbidden_prefixes = (
            "symphonia.application",
            "symphonia.infrastructure",
            "symphonia.runtime",
        )
        violations = []
        for layer in ("providers", "identity"):
            for path in sorted((SOURCE_ROOT / layer).glob("*.py")):
                for module in _absolute_imports(path):
                    if module.startswith(forbidden_prefixes):
                        violations.append(f"{path.relative_to(ROOT)} imports {module}")
        self.assertEqual(violations, [])

    def test_application_does_not_import_runtime_or_concrete_provider_adapters(self) -> None:
        forbidden_prefixes = (
            "symphonia.runtime",
            "symphonia.providers.spotify",
            "symphonia.providers.youtube",
            "symphonia.providers.apple_music",
        )
        violations = []
        for path in sorted((SOURCE_ROOT / "application").glob("*.py")):
            for module in _absolute_imports(path):
                if module == "symphonia.providers" or module.startswith(forbidden_prefixes):
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
        self.assertEqual(violations, [])

    def test_provider_adapters_do_not_import_sibling_adapters(self) -> None:
        adapter_names = {"spotify", "youtube", "apple_music"}
        violations = []
        for adapter_name in sorted(adapter_names):
            path = SOURCE_ROOT / "providers" / f"{adapter_name}.py"
            forbidden = tuple(
                f"symphonia.providers.{other}" for other in adapter_names - {adapter_name}
            )
            for module in _absolute_imports(path):
                if module.startswith(forbidden):
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
