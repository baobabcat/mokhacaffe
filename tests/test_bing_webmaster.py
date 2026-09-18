import importlib.util
import io
import unittest
import urllib.error
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


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

    def test_call_retries_bing_throttle_before_succeeding(self):
        throttle = urllib.error.HTTPError(
            "https://ssl.bing.com/example",
            400,
            "Bad Request",
            Message(),
            io.BytesIO(b'{"ErrorCode":5,"Message":"ERROR!!! ThrottleHost"}'),
        )
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"d":{"Url":"https://mokhacaffe.com/"}}'

        with (
            patch.dict("os.environ", {"BING_WEBMASTER_API_KEY": "test-key"}),
            patch.object(
                bing_webmaster.urllib.request,
                "urlopen",
                side_effect=[throttle, response],
            ) as urlopen,
            patch("time.sleep") as sleep,
        ):
            result = bing_webmaster.call(
                "GetUrlInfo",
                {"siteUrl": bing_webmaster.SITE, "url": bing_webmaster.SITE},
            )

        self.assertEqual(result["d"]["Url"], bing_webmaster.SITE)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_call_does_not_retry_non_400_with_throttle_marker(self):
        error = urllib.error.HTTPError(
            "https://ssl.bing.com/example",
            500,
            "Server Error",
            Message(),
            io.BytesIO(b'{"Message":"ThrottleHost"}'),
        )

        with (
            patch.dict("os.environ", {"BING_WEBMASTER_API_KEY": "test-key"}),
            patch.object(
                bing_webmaster.urllib.request,
                "urlopen",
                side_effect=error,
            ) as urlopen,
            patch("time.sleep") as sleep,
            self.assertRaises(SystemExit),
        ):
            bing_webmaster.call("GetUrlInfo")

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_call_detects_throttle_beyond_display_excerpt_and_backs_off_twice(self):
        throttle_late = urllib.error.HTTPError(
            "https://ssl.bing.com/example",
            400,
            "Bad Request",
            Message(),
            io.BytesIO(b"x" * 350 + b"ThrottleHost"),
        )
        throttle_again = urllib.error.HTTPError(
            "https://ssl.bing.com/example",
            400,
            "Bad Request",
            Message(),
            io.BytesIO(b'{"Message":"ThrottleHost"}'),
        )
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"d":{}}'

        with (
            patch.dict("os.environ", {"BING_WEBMASTER_API_KEY": "test-key"}),
            patch.object(
                bing_webmaster.urllib.request,
                "urlopen",
                side_effect=[throttle_late, throttle_again, response],
            ) as urlopen,
            patch("time.sleep") as sleep,
        ):
            result = bing_webmaster.call("GetUrlInfo")

        self.assertEqual(result, {"d": {}})
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([item.args[0] for item in sleep.call_args_list], [2, 4])

    def test_readable_dates_preserves_unrepresentable_microsoft_dates(self):
        values = [
            "/Date(999999999999999999999999)/",
            f"/Date({'9' * 5000})/",
        ]

        self.assertEqual(bing_webmaster.readable_dates(values), values)


if __name__ == "__main__":
    unittest.main()
