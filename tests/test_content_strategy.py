import json
from html.parser import HTMLParser
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
PUBLIC = ROOT / "public"
HUB_PATH = "/better-coffee-at-home/"
HUB_FILE = PUBLIC / "better-coffee-at-home" / "index.html"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.h1_count = 0
        self.metas = []
        self.links = []
        self.anchors = []
        self.jsonld = []
        self.in_jsonld = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "meta":
            self.metas.append(attributes)
        elif tag == "link":
            self.links.append(attributes)
        elif tag == "a" and attributes.get("href"):
            self.anchors.append(attributes["href"])
        elif tag == "script" and attributes.get("type") == "application/ld+json":
            self.in_jsonld = True
            self.jsonld.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "script":
            self.in_jsonld = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_jsonld and self.jsonld:
            self.jsonld[-1] += data


def parse(path):
    parser = PageParser()
    parser.feed(path.read_text())
    return parser


class ContentStrategyTests(unittest.TestCase):
    def test_better_coffee_hub_has_search_and_share_metadata(self):
        self.assertTrue(HUB_FILE.exists())
        page = parse(HUB_FILE)
        description = next(
            (item.get("content", "") for item in page.metas if item.get("name") == "description"),
            "",
        )
        canonical = [
            item.get("href")
            for item in page.links
            if "canonical" in item.get("rel", "")
        ]

        self.assertIn("better coffee at home", page.title.lower())
        self.assertLessEqual(len(page.title.strip()), 60)
        self.assertGreaterEqual(len(description), 50)
        self.assertLessEqual(len(description), 170)
        self.assertEqual(canonical, ["https://mokhacaffe.com/better-coffee-at-home/"])
        self.assertEqual(page.h1_count, 1)
        self.assertTrue(any(json.loads(block) for block in page.jsonld))

    def test_hub_is_discoverable_from_home_journal_and_sitemap(self):
        self.assertIn(HUB_PATH, parse(PUBLIC / "index.html").anchors)
        self.assertIn(HUB_PATH, parse(PUBLIC / "journal" / "index.html").anchors)

        sitemap = ET.parse(PUBLIC / "sitemap.xml")
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in sitemap.findall("s:url/s:loc", namespace)]
        self.assertIn("https://mokhacaffe.com/better-coffee-at-home/", urls)

    def test_every_indexable_page_title_fits_search_results(self):
        for path in PUBLIC.rglob("index.html"):
            with self.subTest(path=path.relative_to(PUBLIC)):
                self.assertLessEqual(len(parse(path).title.strip()), 60)


if __name__ == "__main__":
    unittest.main()
