from pathlib import Path
import unittest

from tools.validate_specs import validate


class SpecValidatorTests(unittest.TestCase):
    def test_repository_specifications_are_consistent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(validate(root), [])


if __name__ == "__main__":
    unittest.main()
