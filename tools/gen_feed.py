#!/usr/bin/env python3
"""Generate public/feed.xml (Atom 1.0) for the Mokha Caffè journal.

Source of truth: public/journal/index.html <ul class="post-list"> entries
(date · category, title link, summary). Pure stdlib, deterministic output
(no build timestamps — feed <updated> comes from entry dates only), so the
file only changes when journal content changes.

Usage: python3 tools/gen_feed.py          # writes public/feed.xml
       python3 tools/gen_feed.py --check  # verify existing feed is in sync
"""
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "public" / "journal" / "index.html"
OUT = ROOT / "public" / "feed.xml"

SITE = "https://mokhacaffe.com"
FEED_TITLE = "Mokha Caffè — Journal"
FEED_SUBTITLE = ("Notes from the build of Mokha Caffè: brew guides, sourcing "
                 "research, and coffee history worth getting right.")
FEED_ID = f"{SITE}/journal/"
SELF_LINK = f"{SITE}/feed.xml"
ATOM = "http://www.w3.org/2005/Atom"


class PostListParser(HTMLParser):
    """Extract (date, title, href, summary) from the journal index post-list."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.posts = []
        self._in_list = False
        self._li = None          # dict accumulator for current <li>
        self._capture = None     # 'meta' | 'title' | 'summary'
        self._href = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "ul" and "post-list" in a.get("class", ""):
            self._in_list = True
        elif self._in_list and tag == "li":
            self._li = {"meta": "", "title": "", "summary": "", "href": None}
        elif self._li is not None and tag == "p":
            cls = a.get("class", "")
            if "post-meta" in cls:
                self._capture = "meta"
            elif self._li["title"]:  # the trailing summary <p> (no class)
                self._capture = "summary"
        elif self._li is not None and tag == "a" and "title" in a.get("class", ""):
            self._capture = "title"
            self._li["href"] = a.get("href")

    def handle_endtag(self, tag):
        if tag == "ul" and self._in_list:
            self._in_list = False
        elif tag == "li" and self._li is not None:
            self.posts.append(self._li)
            self._li = None
        elif tag in ("p", "a"):
            self._capture = None

    def handle_data(self, data):
        if self._li is None or not self._capture:
            return
        self._li[self._capture] += data


def load_posts():
    p = PostListParser()
    p.feed(INDEX.read_text(encoding="utf-8"))
    posts = []
    for raw in p.posts:
        date = raw["meta"].split("·")[0].strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise SystemExit(f"unparseable post date: {raw['meta']!r}")
        if not (raw["href"] and raw["title"].strip()):
            raise SystemExit(f"post missing href/title: {raw!r}")
        posts.append({
            "date": date,
            "title": " ".join(raw["title"].split()),
            "url": SITE + raw["href"],
            "summary": " ".join(raw["summary"].split()),
        })
    if not posts:
        raise SystemExit("no journal posts found in index — parser drifted?")
    posts.sort(key=lambda x: x["date"], reverse=True)
    return posts


def build_feed(posts):
    ET.register_namespace("", ATOM)
    feed = ET.Element(f"{{{ATOM}}}feed")
    ET.SubElement(feed, f"{{{ATOM}}}title").text = FEED_TITLE
    ET.SubElement(feed, f"{{{ATOM}}}subtitle").text = FEED_SUBTITLE
    ET.SubElement(feed, f"{{{ATOM}}}id").text = FEED_ID
    ET.SubElement(feed, f"{{{ATOM}}}updated").text = f"{posts[0]['date']}T00:00:00Z"
    ET.SubElement(feed, f"{{{ATOM}}}link", rel="alternate",
                  type="text/html", href=FEED_ID)
    ET.SubElement(feed, f"{{{ATOM}}}link", rel="self",
                  type="application/atom+xml", href=SELF_LINK)
    author = ET.SubElement(feed, f"{{{ATOM}}}author")
    ET.SubElement(author, f"{{{ATOM}}}name").text = "Mokha Caffè"
    ET.SubElement(author, f"{{{ATOM}}}uri").text = f"{SITE}/"
    for post in posts:
        e = ET.SubElement(feed, f"{{{ATOM}}}entry")
        ET.SubElement(e, f"{{{ATOM}}}title").text = post["title"]
        ET.SubElement(e, f"{{{ATOM}}}link", rel="alternate",
                      type="text/html", href=post["url"])
        ET.SubElement(e, f"{{{ATOM}}}id").text = post["url"]
        ET.SubElement(e, f"{{{ATOM}}}published").text = f"{post['date']}T00:00:00Z"
        ET.SubElement(e, f"{{{ATOM}}}updated").text = f"{post['date']}T00:00:00Z"
        ET.SubElement(e, f"{{{ATOM}}}summary", type="text").text = post["summary"]
    xml = ET.tostring(feed, encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + xml + "\n"


def main():
    posts = load_posts()
    feed = build_feed(posts)
    if "--check" in sys.argv:
        existing = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if existing != feed:
            raise SystemExit("feed.xml out of sync — run tools/gen_feed.py")
        print(f"feed.xml in sync ({len(posts)} entries)")
        return
    OUT.write_text(feed, encoding="utf-8")
    # self-verify the artifact parses and carries required Atom elements
    parsed = ET.fromstring(feed)
    entries = parsed.findall(f"{{{ATOM}}}entry")
    assert len(entries) == len(posts), "entry count mismatch"
    for e in entries:
        for req in ("title", "id", "updated", "link"):
            assert e.find(f"{{{ATOM}}}{req}") is not None, f"entry missing {req}"
    print(f"wrote {OUT.relative_to(ROOT)} ({len(entries)} entries, "
          f"updated {posts[0]['date']})")


if __name__ == "__main__":
    main()
