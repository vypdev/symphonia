"""Offline review-fixture guardrails; not production UI acceptance tests."""

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


FIXTURE = Path(__file__).resolve().parents[1] / "docs/development/ui-spike"


class FixtureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))


class UiSpikeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (FIXTURE / "index.html").read_text(encoding="utf-8")
        cls.css = (FIXTURE / "styles.css").read_text(encoding="utf-8")
        cls.script = (FIXTURE / "demo.js").read_text(encoding="utf-8")
        cls.parser = FixtureParser()
        cls.parser.feed(cls.html)

    def test_fixture_sections_have_unique_ids_and_navigation_targets(self) -> None:
        elements = self.parser.elements
        ids = [attrs["id"] for _, attrs in elements if attrs.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        views = {attrs["id"] for _, attrs in elements if "view" in (attrs.get("class") or "").split()}
        links = {attrs["data-section"] for tag, attrs in elements if tag == "a" and attrs.get("data-section")}
        self.assertEqual(views, links)
        self.assertEqual(views, {"connections", "library", "copy", "activity"})
        for _, attrs in elements:
            if attrs.get("aria-labelledby"):
                self.assertIn(attrs["aria-labelledby"], ids)
        self.assertIn(('main', {'id': 'main', 'tabindex': '-1'}), elements)

    def test_fixture_cannot_issue_actions_or_load_remote_assets(self) -> None:
        for tag, attrs in self.parser.elements:
            if tag == "button" and attrs.get("id") != "theme-toggle":
                self.assertIn("disabled", attrs)
            for name in ("href", "src", "action"):
                value = attrs.get(name)
                if value is None:
                    continue
                self.assertFalse(value.startswith(("http:", "https:", "//", "/", "javascript:")), (tag, name, value))
            self.assertFalse(any(name.lower().startswith("on") for name in attrs), (tag, attrs))
        self.assertNotIn("fetch(", self.script)
        self.assertNotIn("XMLHttpRequest", self.script)
        self.assertNotIn("localStorage", self.script)
        self.assertNotIn("sessionStorage", self.script)
        self.assertNotIn("innerHTML", self.script)

    def test_theme_and_responsive_fallbacks_are_explicit(self) -> None:
        self.assertIn(":root.theme-dark", self.css)
        self.assertIn("@media (max-width: 620px)", self.css)
        self.assertIn("prefers-reduced-motion: reduce", self.css)
        self.assertIn("forced-colors: active", self.css)
        self.assertIn("safe-area-inset-bottom", self.css)
        self.assertIn(":focus-visible", self.css)
        self.assertIn("aria-current", self.script)
        self.assertNotRegex(self.css, r"url\(\s*['\"]?https?://")

    def test_visible_statuses_are_words_not_color_only(self) -> None:
        statuses = re.findall(r'<span class="status [^"]+">([^<]+)</span>', self.html)
        self.assertGreaterEqual(len(statuses), 10)
        self.assertTrue(all(status.strip() for status in statuses))
        self.assertIn("No destination changes", self.html)
        self.assertIn("no success is inferred", self.html)


if __name__ == "__main__":
    unittest.main()
