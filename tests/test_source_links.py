import sys
from pathlib import Path
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_sources


class SourceLinkTests(unittest.TestCase):
    def test_collect_source_links_only_from_article_pages(self):
        pages = {
            "article.html": """
                <script type="application/ld+json">{"@type":"Article"}</script>
                <a href="https://example.org/source#section">Source</a>
                <a href="https://mokhacaffe.com/contact/">Internal</a>
                <a href="/journal/">Journal</a>
            """,
            "index.html": '<a href="https://example.org/not-editorial">Elsewhere</a>',
        }

        links = check_sources.collect_source_links(pages)

        self.assertEqual(
            links,
            {"https://example.org/source#section": ["article.html"]},
        )

    def test_check_links_distinguishes_broken_from_blocked_sources(self):
        links = {
            "https://example.org/gone": ["one.html"],
            "https://example.org/blocked": ["two.html"],
            "https://example.org/timeout": ["three.html"],
        }
        responses = {
            "https://example.org/gone": (404, "https://example.org/gone"),
            "https://example.org/blocked": (403, "https://example.org/blocked"),
            "https://example.org/timeout": (408, "https://example.org/timeout"),
        }

        results = check_sources.check_links(links, responses.__getitem__)

        self.assertEqual(results[0].level, "FAIL")
        self.assertEqual(results[1].level, "WARN")
        self.assertEqual(results[2].level, "WARN")

    def test_run_fails_only_for_confirmed_broken_sources(self):
        article = """
            <script type="application/ld+json">{"@type":"Article"}</script>
            <a href="https://example.org/source">Source</a>
        """

        output = StringIO()
        with redirect_stdout(output):
            broken = check_sources.run(
                {"article.html": article},
                lambda url: (404, url),
            )
            blocked = check_sources.run(
                {"article.html": article},
                lambda url: (429, url),
            )

        self.assertEqual(broken, 1)
        self.assertEqual(blocked, 0)

    def test_run_warns_when_an_article_has_no_external_source_link(self):
        article = '<script type="application/ld+json">{"@type":"Article"}</script>'
        output = StringIO()

        with redirect_stdout(output):
            status = check_sources.run({"article.html": article}, lambda url: (200, url))

        self.assertEqual(status, 0)
        self.assertIn("[WARN] article.html has no external source link", output.getvalue())

    def test_fetch_url_turns_connection_reset_into_warning_status(self):
        with patch("check_sources.resolved_public_address", return_value="93.184.216.34"), patch(
            "check_sources.request_once", side_effect=ConnectionResetError()
        ):
            status, final_url = check_sources.fetch_url("https://example.org/source")

        self.assertEqual(status, 0)
        self.assertEqual(final_url, "https://example.org/source")

    def test_collect_source_links_normalizes_hosts_and_rejects_missing_hosts(self):
        pages = {
            "article.html": """
                <script type="application/ld+json">{"@type":"Article"}</script>
                <a href="https://MOKHACAFFE.COM/story/">Internal case</a>
                <a href="https://mokhacaffe.com:443/story/">Internal port</a>
                <a href="https:///missing-host">Malformed</a>
                <a href="https://example.org/source">Source</a>
            """
        }

        self.assertEqual(
            check_sources.collect_source_links(pages),
            {"https://example.org/source": ["article.html"]},
        )

    def test_collect_source_links_recognizes_article_in_jsonld_graph(self):
        pages = {
            "article.html": """
                <script type="application/ld+json">
                  {"@graph":[{"@type":["Thing","Article"]}]}
                </script>
                <a href="https://example.org/source">Source</a>
            """
        }

        self.assertEqual(
            check_sources.collect_source_links(pages),
            {"https://example.org/source": ["article.html"]},
        )

    def test_fetch_url_refuses_private_network_targets(self):
        opener = patch("check_sources.request_once")
        with patch(
            "check_sources.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("169.254.169.254", 443))],
        ), opener as mocked_open:
            status, final_url = check_sources.fetch_url("https://metadata.example/source")

        self.assertEqual(status, 0)
        self.assertEqual(final_url, "https://metadata.example/source")
        mocked_open.assert_not_called()

    def test_fetch_url_pins_the_validated_address(self):
        with patch(
            "check_sources.resolved_public_address", return_value="93.184.216.34"
        ), patch(
            "check_sources.request_once", return_value=(200, "https://example.org/source")
        ) as request_once:
            result = check_sources.fetch_url("https://example.org/source")

        self.assertEqual(result, (200, "https://example.org/source"))
        request_once.assert_called_once_with(
            "https://example.org/source", "93.184.216.34"
        )


if __name__ == "__main__":
    unittest.main()
