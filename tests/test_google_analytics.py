import base64
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
MEASUREMENT_ID = "G-HJNKHJZZLL"
EXPECTED_HASH = "sha256-C6tEgffWYngbRtWvVxDfxSFqKsMvTeabRHj1G++2dIY="


class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._inline_script = False
        self.inline_scripts = []
        self.external_scripts = []

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        attributes = dict(attrs)
        src = attributes.get("src")
        if src:
            self.external_scripts.append((src, "async" in attributes))
        else:
            self._inline_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._inline_script = False

    def handle_data(self, data):
        if self._inline_script:
            self.inline_scripts.append(data)


class GoogleAnalyticsTests(unittest.TestCase):
    def test_google_tag_is_on_every_html_page_and_allowed_by_csp(self):
        html_files = sorted(PUBLIC.rglob("*.html"))
        self.assertEqual(9, len(html_files))

        hashes = set()
        expected_src = (
            "https://www.googletagmanager.com/gtag/js?id=" + MEASUREMENT_ID
        )
        for path in html_files:
            parser = ScriptParser()
            parser.feed(path.read_text())
            parser.close()

            self.assertEqual([(expected_src, True)], [
                script for script in parser.external_scripts
                if "googletagmanager.com/gtag/js" in script[0]
            ], path)
            config_scripts = [
                script for script in parser.inline_scripts
                if f"gtag('config', '{MEASUREMENT_ID}');" in script
            ]
            self.assertEqual(1, len(config_scripts), path)
            hashes.add(
                "sha256-"
                + base64.b64encode(
                    hashlib.sha256(config_scripts[0].encode()).digest()
                ).decode()
            )

        self.assertEqual({EXPECTED_HASH}, hashes)
        csp = (PUBLIC / "_headers").read_text()
        for required in (
            EXPECTED_HASH,
            "https://www.googletagmanager.com",
            "https://*.google-analytics.com",
            "https://*.analytics.google.com",
        ):
            self.assertIn(required, csp)
        self.assertNotIn("'unsafe-inline'", csp)


if __name__ == "__main__":
    unittest.main()
