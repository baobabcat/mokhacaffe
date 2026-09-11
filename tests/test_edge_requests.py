import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "tools" / "edge_requests.py"
SPEC = importlib.util.spec_from_file_location("edge_requests", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
edge_requests = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(edge_requests)


def group(count, path, status=200, method="GET", referrer="", user_agent="test-agent"):
    return {
        "count": count,
        "dimensions": {
            "clientRequestPath": path,
            "edgeResponseStatus": status,
            "clientRequestHTTPMethodName": method,
            "clientRefererHost": referrer,
            "userAgent": user_agent,
        },
    }


class AcquisitionSummaryTests(unittest.TestCase):
    def test_merge_groups_preserves_request_method(self):
        rows = [
            group(2, "/"),
            group(3, "/"),
        ]

        merged = edge_requests.merge_group_rows(rows)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["count"], 5)
        self.assertEqual(merged[0]["dimensions"]["clientRequestHTTPMethodName"], "GET")

    def test_acquisition_report_shows_canonical_pages(self):
        groups = [
            group(3, "/"),
            group(2, "/journal/"),
            group(8, "/wp-login.php", referrer="spam.example"),
        ]

        report = edge_requests.format_acquisition(groups)

        self.assertIn("canonical content requests: 5", report)
        self.assertIn("3  /", report)
        self.assertIn("2  /journal/", report)
        self.assertNotIn("spam.example", report)
        self.assertNotIn("external referrers", report)

    def test_acquisition_report_shows_calculator_as_canonical_content(self):
        groups = [group(2, "/coffee-ratio-calculator/")]

        self.assertEqual(
            edge_requests.canonical_content_requests(groups),
            {"/coffee-ratio-calculator/": 2},
        )

    def test_acquisition_report_shows_published_hub_and_guides(self):
        groups = [
            group(2, "/better-coffee-at-home/"),
            group(3, "/journal/how-to-read-a-coffee-bag/"),
            group(4, "/journal/coffee-bean-types/"),
        ]

        self.assertEqual(
            edge_requests.canonical_content_requests(groups),
            {
                "/better-coffee-at-home/": 2,
                "/journal/how-to-read-a-coffee-bag/": 3,
                "/journal/coffee-bean-types/": 4,
            },
        )

    def test_acquisition_report_separates_known_crawlers_from_other_requests(self):
        groups = [
            group(4, "/journal/coffee-bean-types/", user_agent="Googlebot/2.1"),
            group(3, "/journal/coffee-bean-types/", user_agent="Mozilla/5.0"),
        ]

        report = edge_requests.format_acquisition(groups)

        self.assertIn("canonical content requests with a known crawler signature: 4", report)
        self.assertIn("other canonical content requests: 3", report)
        self.assertIn("not verified human visits", report)
        self.assertEqual(sum(edge_requests.canonical_content_request_split(groups)), 7)

    def test_acquisition_report_breaks_known_crawlers_down_by_canonical_path(self):
        groups = [
            group(2, "/story/", user_agent="Googlebot/2.1"),
            group(3, "/journal/coffee-bean-types/", user_agent="bingbot/2.0"),
            group(4, "/journal/coffee-bean-types/", user_agent="Mozilla/5.0"),
            group(5, "/robots.txt", user_agent="Googlebot/2.1"),
        ]

        report = edge_requests.format_acquisition(groups)

        self.assertIn("known crawler signatures by canonical path:", report)
        self.assertIn("     3  bingbot  /journal/coffee-bean-types/", report)
        self.assertIn("     2  googlebot  /story/", report)
        self.assertNotIn("5  googlebot  /robots.txt", report)

    def test_query_requests_method_but_not_unavailable_referrer(self):
        self.assertIn("clientRequestHTTPMethodName", edge_requests.QUERY)
        self.assertNotIn("clientRefererHost", edge_requests.QUERY)

    def test_canonical_content_requests_exclude_assets_errors_and_unsafe_methods(self):
        groups = [
            group(4, "/"),
            group(3, "/journal/", method="HEAD"),
            group(8, "/assets/styles.css"),
            group(5, "/story/", status=404),
            group(6, "/contact/", method="POST"),
        ]

        self.assertEqual(
            edge_requests.canonical_content_requests(groups),
            {"/": 4, "/journal/": 3},
        )


if __name__ == "__main__":
    unittest.main()
