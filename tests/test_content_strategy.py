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
        self.h1_text = ""
        self.in_h1 = False
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
            self.in_h1 = True
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
        elif tag == "h1":
            self.in_h1 = False
        elif tag == "script":
            self.in_jsonld = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_h1:
            self.h1_text += data
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

    def test_coffee_bag_guide_is_published_and_connected_to_hub(self):
        guide_path = "/journal/how-to-read-a-coffee-bag/"
        guide = parse(PUBLIC / "journal" / "how-to-read-a-coffee-bag" / "index.html")
        articles = [
            json.loads(block)
            for block in guide.jsonld
            if json.loads(block).get("@type") == "Article"
        ]

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].get("datePublished"), "2026-09-09")
        self.assertIn(HUB_PATH, guide.anchors)
        self.assertIn(guide_path, parse(PUBLIC / "index.html").anchors)
        self.assertIn(guide_path, parse(PUBLIC / "journal" / "index.html").anchors)
        self.assertIn(guide_path, parse(HUB_FILE).anchors)

        sitemap = ET.parse(PUBLIC / "sitemap.xml")
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in sitemap.findall("s:url/s:loc", namespace)]
        self.assertIn("https://mokhacaffe.com" + guide_path, urls)

    def test_qishr_article_links_to_its_named_sources(self):
        article = parse(
            PUBLIC / "journal" / "qishr-yemeni-ginger-coffee" / "index.html"
        )
        for source in (
            "https://en.wikipedia.org/wiki/Qishr",
            "https://en.wikipedia.org/wiki/Coffee_cherry_tea",
        ):
            with self.subTest(source=source):
                self.assertIn(source, article.anchors)

    def test_moka_pot_article_links_to_bialetti_guidance(self):
        article_path = PUBLIC / "journal" / "moka-pot-properly" / "index.html"
        article = parse(article_path)
        for source in (
            "https://www.bialetti.com/it_en/moka-express.html",
            "https://www.bialetti.com/it_en/inspiration/post/ground-coffee-for-moka-should-never-be-pressed",
        ):
            with self.subTest(source=source):
                self.assertIn(source, article.anchors)

        article_data = next(
            json.loads(block)
            for block in article.jsonld
            if json.loads(block).get("@type") == "Article"
        )
        self.assertEqual(article_data.get("datePublished"), "2026-08-25")
        self.assertEqual(article_data.get("dateModified"), "2026-09-13")
        self.assertIn("Updated 2026-09-13", article_path.read_text())

        sitemap = ET.parse(PUBLIC / "sitemap.xml")
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        lastmods = {
            node.findtext("s:loc", namespaces=namespace): node.findtext(
                "s:lastmod", namespaces=namespace
            )
            for node in sitemap.findall("s:url", namespace)
        }
        self.assertEqual(
            lastmods["https://mokhacaffe.com/journal/moka-pot-properly/"],
            article_data["dateModified"],
        )

    def test_story_headline_matches_emerging_search_intent(self):
        story = parse(PUBLIC / "story" / "index.html")
        headline = story.h1_text.lower()
        self.assertIn("al-mokha", headline)
        self.assertIn("port", headline)
        self.assertIn("coffee", headline)

    def test_story_has_article_structured_data(self):
        story = parse(PUBLIC / "story" / "index.html")
        blocks = [json.loads(block) for block in story.jsonld]
        articles = [block for block in blocks if block.get("@type") == "Article"]
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].get("url"), "https://mokhacaffe.com/story/")
        self.assertEqual(articles[0].get("headline"), "Al-Mokha: the port that named coffee")

    def test_coffee_bean_types_guide_is_published_and_connected(self):
        guide_path = "/journal/coffee-bean-types/"
        guide_file = PUBLIC / "journal" / "coffee-bean-types" / "index.html"
        self.assertTrue(guide_file.exists())

        guide = parse(guide_file)
        description = next(
            (item.get("content", "") for item in guide.metas if item.get("name") == "description"),
            "",
        )
        canonical = [
            item.get("href")
            for item in guide.links
            if "canonical" in item.get("rel", "")
        ]
        articles = [
            json.loads(block)
            for block in guide.jsonld
            if json.loads(block).get("@type") == "Article"
        ]

        self.assertIn("coffee bean types", guide.title.lower())
        self.assertEqual(guide.h1_count, 1)
        self.assertGreaterEqual(len(description), 50)
        self.assertLessEqual(len(description), 170)
        self.assertEqual(canonical, ["https://mokhacaffe.com" + guide_path])
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].get("datePublished"), "2026-09-09")
        self.assertEqual(articles[0].get("image"), "https://mokhacaffe.com/assets/og.png")
        self.assertIn('class="dropcap">A&nbsp;bag ', guide_file.read_text())

        for source in (
            PUBLIC / "index.html",
            PUBLIC / "journal" / "index.html",
            HUB_FILE,
        ):
            with self.subTest(source=source.relative_to(PUBLIC)):
                self.assertIn(guide_path, parse(source).anchors)

        for target in (
            HUB_PATH,
            "/journal/how-to-read-a-coffee-bag/",
            "/coffee-ratio-calculator/",
        ):
            with self.subTest(target=target):
                self.assertIn(target, guide.anchors)

        sitemap = ET.parse(PUBLIC / "sitemap.xml")
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in sitemap.findall("s:url/s:loc", namespace)]
        self.assertIn("https://mokhacaffe.com" + guide_path, urls)

    def test_grind_size_chart_is_published_and_connected(self):
        chart_path = "/coffee-grind-size-chart/"
        chart_file = PUBLIC / "coffee-grind-size-chart" / "index.html"
        self.assertTrue(chart_file.exists())

        chart = parse(chart_file)
        description = next(
            (item.get("content", "") for item in chart.metas if item.get("name") == "description"),
            "",
        )
        canonical = [
            item.get("href")
            for item in chart.links
            if "canonical" in item.get("rel", "")
        ]
        articles = [
            json.loads(block)
            for block in chart.jsonld
            if json.loads(block).get("@type") == "Article"
        ]

        self.assertIn("coffee grind size chart", chart.title.lower())
        self.assertEqual(chart.h1_count, 1)
        self.assertGreaterEqual(len(description), 50)
        self.assertLessEqual(len(description), 170)
        self.assertEqual(canonical, ["https://mokhacaffe.com" + chart_path])
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].get("datePublished"), "2026-09-11")
        self.assertEqual(articles[0].get("image"), "https://mokhacaffe.com/assets/og.png")

        html = chart_file.read_text()
        self.assertIn("<table", html)
        self.assertIn('class="table-wrap"', html)
        styles = (PUBLIC / "assets" / "styles.css").read_text()
        self.assertIn(".table-wrap", styles)
        self.assertIn("overflow-x: auto", styles)
        self.assertIn("French press", html)
        self.assertIn("Moka pot", html)
        self.assertIn("Pour-over", html)
        self.assertIn("AeroPress", html)
        self.assertIn("Espresso", html)

        for source in (
            PUBLIC / "index.html",
            HUB_FILE,
            PUBLIC / "coffee-ratio-calculator" / "index.html",
            PUBLIC / "journal" / "moka-pot-properly" / "index.html",
        ):
            with self.subTest(source=source.relative_to(PUBLIC)):
                self.assertIn(chart_path, parse(source).anchors)

        for target in (
            HUB_PATH,
            "/coffee-ratio-calculator/",
            "/journal/moka-pot-properly/",
        ):
            with self.subTest(target=target):
                self.assertIn(target, chart.anchors)

        sitemap = ET.parse(PUBLIC / "sitemap.xml")
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in sitemap.findall("s:url/s:loc", namespace)]
        self.assertIn("https://mokhacaffe.com" + chart_path, urls)

    def test_article_structured_data_has_search_image(self):
        article_pages = 0
        for path in PUBLIC.rglob("index.html"):
            blocks = [json.loads(block) for block in parse(path).jsonld]
            for block in blocks:
                if block.get("@type") == "Article":
                    article_pages += 1
                    with self.subTest(path=path.relative_to(PUBLIC)):
                        self.assertEqual(
                            block.get("image"),
                            "https://mokhacaffe.com/assets/og.png",
                        )
        self.assertGreater(article_pages, 0)

    def test_every_indexable_page_has_start_here_navigation(self):
        for path in PUBLIC.rglob("index.html"):
            with self.subTest(path=path.relative_to(PUBLIC)):
                self.assertIn(HUB_PATH, parse(path).anchors)

    def test_every_indexable_page_has_a_visible_journal_feed_link(self):
        for path in PUBLIC.rglob("index.html"):
            with self.subTest(path=path.relative_to(PUBLIC)):
                self.assertIn("/feed.xml", parse(path).anchors)

    def test_every_indexable_page_title_fits_search_results(self):
        for path in PUBLIC.rglob("index.html"):
            with self.subTest(path=path.relative_to(PUBLIC)):
                self.assertLessEqual(len(parse(path).title.strip()), 60)

    def test_public_email_addresses_use_the_official_domain(self):
        official_email = "hello@mokhacaffe.com"
        contact_html = (PUBLIC / "contact" / "index.html").read_text()
        self.assertIn(f'href="mailto:{official_email}', contact_html)
        self.assertIn(f">{official_email}</a>", contact_html)
        self.assertNotIn("interim address", contact_html.lower())
        self.assertNotIn("mail routing is being set up", contact_html.lower())

        for path in PUBLIC.rglob("*.html"):
            with self.subTest(path=path.relative_to(PUBLIC)):
                html = path.read_text()
                for href in parse(path).anchors:
                    if href.startswith("mailto:"):
                        self.assertEqual(official_email, href.removeprefix("mailto:").split("?", 1)[0])
                self.assertNotIn("baobabcatllc@icloud.com", html.lower())


if __name__ == "__main__":
    unittest.main()
