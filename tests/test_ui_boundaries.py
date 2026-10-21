"""Exercise the UI boundary checks against isolated nested source fixtures."""

from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UiBoundaryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for UI boundary fixtures")
    def test_nested_sources_and_symlinks_cannot_bypass_either_boundary_check(self) -> None:
        for script in ("ui/scripts/check-boundary.mjs", "docs/development/ui-lit-spike/scripts/check-boundary.mjs"):
            for kind in ("pure", "browser", "outer", "symlink"):
                with self.subTest(script=script, kind=kind), TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / "src" / "nested").mkdir(parents=True)
                    (root / "src/main.ts").write_text('import "./nested/helper.ts";\n')
                    helper = root / "src/nested/helper.ts"
                    helper.write_text({"pure": "export const value = 1;", "browser": 'fetch("/unsafe");', "outer": 'import "provider-sdk";', "symlink": "export const value = 1;"}[kind])
                    if kind == "symlink":
                        outside = root / "outside.ts"
                        outside.write_text("export const value = 1;")
                        (root / "src/escape.ts").symlink_to(outside)
                    result = subprocess.run(["node", str(ROOT / script)], cwd=root, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode == 0, kind == "pure", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
