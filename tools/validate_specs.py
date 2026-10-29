"""Compatibility entrypoint for the unchanged Copilot specification validator.

The specification policy and catalog renderer belong to Copilot. This module
only preserves the Python command used by existing contributor tooling.
"""

import argparse
from pathlib import Path
import subprocess


VALIDATOR = Path(__file__).resolve().parents[1] / "scripts/validate-specification-catalog.cjs"


def validate(root: Path) -> list[str]:
    """Return diagnostics from Copilot without translating its catalog dialect."""
    try:
        result = subprocess.run(
            ["node", "-e", "require(process.argv[1]).main([], process.argv[2])",
             str(VALIDATOR), str(root.resolve())],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return [f"Cannot run the Copilot specification validator: {error}"]
    return [] if result.returncode == 0 else (result.stderr.strip().splitlines() or ["Copilot specification validation failed."])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Copilot specification validation")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = validate(args.root)
    if errors:
        print("\n".join(errors))
        return 1
    print("Copilot specification catalog validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
