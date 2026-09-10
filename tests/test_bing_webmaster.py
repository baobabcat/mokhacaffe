import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "bing_webmaster", ROOT / "tools" / "bing_webmaster.py"
)
assert SPEC is not None
bing_webmaster = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bing_webmaster)


class BingWebmasterOutputTests(unittest.TestCase):
    def test_crawl_stats_prints_bing_dates_as_utc_iso_dates(self):
        payload = {
            "d": [
                {
                    "Date": "/Date(1788220800000)/",
                    "CrawledPages": 4,
                }
            ]
        }

        with patch.object(bing_webmaster, "call", return_value=payload):
            output = io.StringIO()
            with redirect_stdout(output):
                bing_webmaster._stats("GetCrawlStats")

        self.assertIn('"Date": "2026-09-01T00:00:00Z"', output.getvalue())
        self.assertNotIn("/Date(", output.getvalue())

    def test_url_info_prints_missing_date_sentinel_as_an_iso_date(self):
        payload = {
            "d": {
                "DiscoveryDate": "/Date(-62135596800000)/",
                "LastCrawledDate": "/Date(-62135596800000)/",
                "HttpStatus": 0,
            }
        }

        with patch.object(bing_webmaster, "call", return_value=payload):
            output = io.StringIO()
            with redirect_stdout(output):
                bing_webmaster.cmd_urlinfo(SimpleNamespace(url="https://example.com/"))

        self.assertIn('"DiscoveryDate": "0001-01-01T00:00:00Z"', output.getvalue())
        self.assertIn('"LastCrawledDate": "0001-01-01T00:00:00Z"', output.getvalue())
        self.assertNotIn("/Date(", output.getvalue())

    def test_readable_dates_preserves_unrepresentable_microsoft_dates(self):
        values = [
            "/Date(999999999999999999999999)/",
            f"/Date({'9' * 5000})/",
        ]

        self.assertEqual(bing_webmaster.readable_dates(values), values)


if __name__ == "__main__":
    unittest.main()
