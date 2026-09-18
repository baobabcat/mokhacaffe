from email.message import Message
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import urllib.error


class FakeResponse:
    status = 200
    headers = {"Content-Type": "text/html"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return b"ok"

    def geturl(self):
        return "https://mokhacaffe.com/"


MODULE_PATH = Path(__file__).parents[1] / "tools" / "health_check.py"
HEALTH_WRAPPER = Path(__file__).parents[1] / "operations" / "mokhacaffe-health.sh"
SPEC = importlib.util.spec_from_file_location("health_check", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
health_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health_check)


class HealthCheckTests(unittest.TestCase):
    def test_canonical_urls_are_derived_from_sitemap(self):
        sitemap = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <url><loc>https://mokhacaffe.com/</loc></url>
  <url><loc>https://mokhacaffe.com/better-coffee-at-home/</loc></url>
</urlset>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            path.write_text(sitemap, encoding="utf-8")

            self.assertEqual(
                health_check.sitemap_urls(path),
                [
                    "https://mokhacaffe.com/",
                    "https://mokhacaffe.com/better-coffee-at-home/",
                ],
            )

    def test_sitemap_rejects_an_unexpected_origin(self):
        sitemap = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <url><loc>https://other.example/private/</loc></url>
</urlset>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            path.write_text(sitemap, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unexpected sitemap origin"):
                health_check.sitemap_urls(path)

    def test_fetch_uses_the_identifiable_site_check_user_agent(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse()

        result = health_check.fetch("https://mokhacaffe.com/", opener=opener)

        self.assertEqual(result.status, 200)
        self.assertEqual(result.body, b"ok")
        self.assertEqual(requests[0][0].get_header("User-agent"), health_check.USER_AGENT)
        self.assertEqual(requests[0][1], 20)

    def test_fetch_returns_http_error_status_and_body_for_expected_404(self):
        headers = Message()
        headers["Content-Type"] = "text/html"
        error = urllib.error.HTTPError(
            "https://mokhacaffe.com/nope",
            404,
            "Not Found",
            headers,
            io.BytesIO(b"branded missing page"),
        )

        def opener(_request, timeout):
            self.assertEqual(timeout, 20)
            raise error

        result = health_check.fetch("https://mokhacaffe.com/nope", opener=opener)

        self.assertEqual(result.status, 404)
        self.assertEqual(result.body, b"branded missing page")

    def test_health_matrix_includes_every_sitemap_url(self):
        canonical_urls = [
            "https://mokhacaffe.com/",
            "https://mokhacaffe.com/better-coffee-at-home/",
            "https://mokhacaffe.com/new-guide/",
        ]

        checks = health_check.build_checks(canonical_urls)

        checked_urls = [check.url for check in checks]
        for url in canonical_urls:
            self.assertIn(url, checked_urls)

    def test_health_matrix_keeps_noncanonical_operational_targets(self):
        checks = health_check.build_checks(["https://mokhacaffe.com/"])
        expected = {
            "https://mokhacaffe.com/sitemap.xml": 200,
            "https://mokhacaffe.com/feed.xml": 200,
            "https://mokhacaffe.com/robots.txt": 200,
            "https://mokhacaffe.com/assets/og.png": 200,
            "https://mokhacaffe.com/assets/favicon.svg": 200,
            "https://mokhacaffe.com/assets/ratio-calculator.mjs": 200,
            "https://mokhacaffe.com/assets/ratio-calculator-page.mjs": 200,
            "https://mokhacaffe.com/79ab30351487365090c7d6b534c3dbb4.txt": 200,
            "https://mokhacaffe.com/nope-404": 404,
        }

        actual = {check.url: check.expected_status for check in checks}

        for url, status in expected.items():
            self.assertEqual(actual[url], status)

    def test_run_checks_reports_only_failures(self):
        checks = [
            health_check.Check("home", "https://mokhacaffe.com/", 200),
            health_check.Check("missing", "https://mokhacaffe.com/nope", 404),
        ]
        responses = {
            "https://mokhacaffe.com/": health_check.Response(200, {}, b"home"),
            "https://mokhacaffe.com/nope": health_check.Response(200, {}, b"fallback"),
        }

        failures = health_check.run_checks(checks, fetcher=lambda url: responses[url])

        self.assertEqual(
            failures,
            ["missing: got HTTP 200, expected 404 (https://mokhacaffe.com/nope)"],
        )

    def test_run_checks_records_transport_failures_and_continues(self):
        checks = [
            health_check.Check("broken", "https://mokhacaffe.com/broken", 200),
            health_check.Check("home", "https://mokhacaffe.com/", 200),
        ]

        def fetcher(url):
            if url.endswith("/broken"):
                raise urllib.error.URLError("temporary DNS failure")
            return health_check.Response(200, {}, b"home")

        failures = health_check.run_checks(checks, fetcher=fetcher)

        self.assertEqual(
            failures,
            [
                "broken: request failed: temporary DNS failure "
                "(https://mokhacaffe.com/broken)"
            ],
        )

    def test_run_checks_rejects_a_redirected_canonical_target(self):
        requested = "https://mokhacaffe.com/better-coffee-at-home/"
        response = health_check.Response(
            200,
            {},
            b"homepage",
            "https://mokhacaffe.com/",
        )

        failures = health_check.run_checks(
            [health_check.Check("canonical", requested, 200)],
            fetcher=lambda _url: response,
        )

        self.assertEqual(
            failures,
            [
                "canonical: resolved to https://mokhacaffe.com/, expected "
                "https://mokhacaffe.com/better-coffee-at-home/"
            ],
        )

    def test_run_checks_requires_the_branded_404_marker(self):
        check = health_check.Check(
            "branded-404",
            "https://mokhacaffe.com/nope-404",
            404,
        )

        failures = health_check.run_checks(
            [check],
            fetcher=lambda _url: health_check.Response(404, {}, b"generic missing"),
        )

        self.assertEqual(
            failures,
            ["branded-404: expected branded 404 body marker 'Lost off'"],
        )

    def test_home_invariants_require_brand_beacon_and_hsts(self):
        response = health_check.Response(
            200,
            {},
            b"<html><body>placeholder</body></html>",
        )

        failures = health_check.validate_home(response)

        self.assertEqual(
            failures,
            [
                "home-marker: 'Mokha' not found in homepage HTML",
                "beacon: cloudflare web-analytics beacon missing from homepage",
                "hsts: strict-transport-security header missing",
            ],
        )

    def test_check_site_runs_sitemap_matrix_and_home_invariants(self):
        sitemap = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <url><loc>https://mokhacaffe.com/</loc></url>
  <url><loc>https://mokhacaffe.com/better-coffee-at-home/</loc></url>
</urlset>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            path.write_text(sitemap, encoding="utf-8")
            expected = {
                check.url: check.expected_status
                for check in health_check.build_checks(health_check.sitemap_urls(path))
            }

            def fetcher(url):
                if url == health_check.ORIGIN + "/":
                    body = b"Mokha beacon.min.js"
                elif url.endswith("/nope-404"):
                    body = b"Lost off Al-Mokha"
                else:
                    body = b"ok"
                headers = {"Strict-Transport-Security": "max-age=31536000"}
                return health_check.Response(expected[url], headers, body)

            failures = health_check.check_site(path, fetcher=fetcher)

        self.assertEqual(failures, [])

    def test_cron_wrapper_uses_sitemap_health_tool_and_identifiable_redirect_probes(self):
        script = HEALTH_WRAPPER.read_text(encoding="utf-8")

        self.assertIn("python3 tools/health_check.py", script)
        self.assertIn("MokhaVerification/1.0", script)
        self.assertIn("http://mokhacaffe.com/", script)
        self.assertIn("https://www.mokhacaffe.com/", script)
        self.assertIn("%{redirect_url}", script)
        self.assertIn("https://mokhacaffe.com/", script)
        self.assertNotIn("/story/", script)


if __name__ == "__main__":
    unittest.main()
