import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "tools" / "rum_baseline.py"
SPEC = importlib.util.spec_from_file_location("rum_baseline", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
rum_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rum_baseline)


def group(count, path="/", referrer="", bot=0, site=None):
    return {
        "count": count,
        "dimensions": {
            "siteTag": site or rum_baseline.LIVE_SITE,
            "requestHost": "mokhacaffe.com",
            "requestPath": path,
            "refererHost": referrer,
            "bot": bot,
        },
    }


class RumReferralTests(unittest.TestCase):
    def test_canonical_paths_reject_an_unexpected_origin(self):
        sitemap = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <url><loc>https://other.example/</loc></url>
</urlset>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            path.write_text(sitemap, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unexpected sitemap origin"):
                rum_baseline.sitemap_canonical_paths(path)

    def test_canonical_paths_reject_an_empty_urlset(self):
        sitemap = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"></urlset>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            path.write_text(sitemap, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "no canonical URLs"):
                rum_baseline.sitemap_canonical_paths(path)

    def test_canonical_paths_reject_a_sitemap_index(self):
        sitemap = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <sitemap><loc>https://mokhacaffe.com/section-sitemap.xml</loc></sitemap>
</sitemapindex>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            path.write_text(sitemap, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "expected a sitemap urlset"):
                rum_baseline.sitemap_canonical_paths(path)

    def test_query_uses_separate_path_and_referrer_groupings(self):
        compact_query = " ".join(rum_baseline.QUERY.split())

        self.assertIn("pathGroups: rumPageloadEventsAdaptiveGroups", compact_query)
        self.assertIn(
            "dimensions { siteTag requestHost requestPath }",
            compact_query,
        )
        self.assertIn("referrerGroups: rumPageloadEventsAdaptiveGroups", compact_query)
        self.assertIn("dimensions { siteTag refererHost bot }", compact_query)
        self.assertIn("$until: Time!", compact_query)
        self.assertEqual(compact_query.count("datetime_lt: $until"), 2)
        self.assertNotIn(
            "dimensions { siteTag requestHost requestPath refererHost bot }",
            compact_query,
        )

    def test_main_sends_a_shared_bounded_window(self):
        response = {
            "data": {
                "viewer": {
                    "accounts": [{"pathGroups": [], "referrerGroups": []}]
                }
            }
        }
        captured = {}

        def open_request(request, timeout):
            captured.update(json.loads(request.data))
            return io.BytesIO(json.dumps(response).encode())

        with (
            mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"}),
            mock.patch.object(sys, "argv", ["rum_baseline.py"]),
            mock.patch.object(
                rum_baseline.urllib.request,
                "urlopen",
                side_effect=open_request,
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            rum_baseline.main()

        variables = captured["variables"]
        self.assertEqual(variables["acct"], rum_baseline.ACCT)
        self.assertRegex(variables["since"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertRegex(variables["until"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertLess(variables["since"], variables["until"])

    def test_main_uses_path_groups_without_referrer_fragmentation(self):
        response = {
            "data": {
                "viewer": {
                    "accounts": [{
                        "rumPageloadEventsAdaptiveGroups": [
                            group(2, path="/menu", referrer="google.com"),
                            group(3, path="/menu", referrer="bing.com"),
                        ],
                        "pathGroups": [group(5, path="/menu")],
                        "referrerGroups": [group(2, referrer="google.com")],
                    }]
                }
            }
        }
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"}),
            mock.patch.object(sys, "argv", ["rum_baseline.py"]),
            mock.patch.object(
                rum_baseline.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            rum_baseline.main()

        output = stdout.getvalue()
        self.assertEqual(output.count("mokhacaffe.com/menu"), 1)
        self.assertIn("    5  mokhacaffe.com/menu", output)
        self.assertIn("    2  google.com", output)

    def test_main_separates_canonical_from_noncanonical_pageloads(self):
        response = {
            "data": {
                "viewer": {
                    "accounts": [{
                        "pathGroups": [
                            group(5, path="/"),
                            group(3, path="/definitely-missing"),
                            {
                                "count": 4,
                                "dimensions": {
                                    "siteTag": rum_baseline.LIVE_SITE,
                                    "requestHost": "www.mokhacaffe.com",
                                    "requestPath": "/",
                                    "refererHost": "",
                                    "bot": 0,
                                },
                            },
                        ],
                        "referrerGroups": [],
                    }]
                }
            }
        }
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"}),
            mock.patch.object(sys, "argv", ["rum_baseline.py"]),
            mock.patch.object(
                rum_baseline.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            rum_baseline.main()

        output = stdout.getvalue()
        self.assertIn("canonical pageloads (live site): 5", output)
        self.assertIn("noncanonical or non-apex pageloads (live site): 7", output)
        self.assertIn("total (live site): 12", output)

    def test_main_ignores_path_rows_with_missing_or_null_dimensions(self):
        response = {
            "data": {
                "viewer": {
                    "accounts": [{
                        "pathGroups": [
                            {"count": 4},
                            {"count": 3, "dimensions": None},
                            group(2, path="/story/"),
                        ],
                        "referrerGroups": [],
                    }]
                }
            }
        }
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"}),
            mock.patch.object(sys, "argv", ["rum_baseline.py"]),
            mock.patch.object(
                rum_baseline.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            try:
                rum_baseline.main()
            except (KeyError, TypeError, AttributeError) as exc:
                self.fail(f"missing/null dimensions should be ignored: {exc}")

        self.assertIn("    2  mokhacaffe.com/story/", stdout.getvalue())
        self.assertIn("total (live site): 2", stdout.getvalue())

    def test_main_all_sites_includes_non_live_path_groups(self):
        response = {
            "data": {
                "viewer": {
                    "accounts": [{
                        "pathGroups": [
                            group(2, path="/story/"),
                            group(3, path="/legacy/", site="historical-site"),
                        ],
                        "referrerGroups": [],
                    }]
                }
            }
        }
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"}),
            mock.patch.object(sys, "argv", ["rum_baseline.py", "--all-sites"]),
            mock.patch.object(
                rum_baseline.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            rum_baseline.main()

        self.assertIn("mokhacaffe.com/story/", stdout.getvalue())
        self.assertIn("mokhacaffe.com/legacy/", stdout.getvalue())
        self.assertIn("total (live site): 2", stdout.getvalue())

    def test_main_refuses_to_report_when_path_groups_hit_query_limit(self):
        response = {
            "data": {
                "viewer": {
                    "accounts": [{
                        "pathGroups": [group(1, path=f"/{index}") for index in range(100)],
                        "referrerGroups": [],
                    }]
                }
            }
        }
        with (
            mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"}),
            mock.patch.object(sys, "argv", ["rum_baseline.py"]),
            mock.patch.object(
                rum_baseline.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(SystemExit, "pathGroups.*100"),
        ):
            rum_baseline.main()

    def test_main_refuses_to_report_when_referrer_groups_hit_query_limit(self):
        response = {
            "data": {
                "viewer": {
                    "accounts": [{
                        "pathGroups": [],
                        "referrerGroups": [
                            group(1, referrer=f"referrer-{index}.example")
                            for index in range(100)
                        ],
                    }]
                }
            }
        }
        with (
            mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test-token"}),
            mock.patch.object(sys, "argv", ["rum_baseline.py"]),
            mock.patch.object(
                rum_baseline.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(SystemExit, "referrerGroups.*100"),
        ):
            rum_baseline.main()

    def test_external_referrers_exclude_direct_internal_bot_and_other_sites(self):
        groups = [
            group(3, referrer="coffee.stackexchange.com"),
            group(2, referrer="www.google.com"),
            group(7, referrer="mokhacaffe.com"),
            group(6, referrer="SHOP.MOKHACAFFE.COM."),
            group(5, referrer="deep.blog.mokhacaffe.com"),
            group(5),
            group(4, referrer="news.example", bot=1),
            group(8, referrer="other.example", site="other-site"),
        ]

        self.assertEqual(
            rum_baseline.external_referrers(groups),
            {"coffee.stackexchange.com": 3, "www.google.com": 2},
        )

    def test_external_referrers_ignore_missing_and_null_dimensions(self):
        groups = [
            {"count": 4},
            {"count": 3, "dimensions": None},
            {"count": 2, "dimensions": {}},
        ]

        try:
            referrers = rum_baseline.external_referrers(groups)
        except (KeyError, TypeError, AttributeError) as exc:
            self.fail(f"missing/null dimensions should be ignored: {exc}")

        self.assertEqual(referrers, {})

    def test_referrer_report_states_when_no_external_referrer_is_seen(self):
        self.assertIn(
            "none observed",
            rum_baseline.format_referrers([group(2), group(1, referrer="mokhacaffe.com")]),
        )

    def test_referrer_report_lists_external_hosts(self):
        report = rum_baseline.format_referrers([group(3, referrer="coffee.stackexchange.com")])
        self.assertIn("3  coffee.stackexchange.com", report)
        self.assertIn("not unique visitors", report)


if __name__ == "__main__":
    unittest.main()
