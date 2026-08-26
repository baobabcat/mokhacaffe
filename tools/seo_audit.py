#!/usr/bin/env python3
"""Technical SEO audit for mokhacaffe.com (pure stdlib).

Fetches every public page and checks per-page SEO fundamentals plus
cross-page consistency (sitemap, internal links, JSON-LD validity).
Read-only: only GET requests. Exit 0 = pass, 1 = findings.

Usage: python3 tools/seo_audit.py [--base https://mokhacaffe.com]
"""
import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = "mokha-seo-audit/1.0 (read-only technical audit; contact hello@mokhacaffe.com)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = None
        self._in_title = False
        self.metas = []          # list of dicts
        self.links = []          # <link> tags
        self.h1 = []
        self._in_h1 = False
        self.imgs = []           # (src, alt|None)
        self.anchors = []        # hrefs
        self.jsonld = []         # raw json-ld script bodies
        self._in_jsonld = False
        self.html_attrs = {}
        self.lang = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
            self.title = ""
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
            if a.get("rel") == "canonical" or "canonical" in str(a.get("rel", "")):
                pass
        elif tag == "h1":
            self._in_h1 = True
            self.h1.append("")
        elif tag == "img":
            self.imgs.append((a.get("src", ""), a.get("alt")))
        elif tag == "a":
            href = a.get("href")
            if href:
                self.anchors.append(href)
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True
            self.jsonld.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "script":
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_title and self.title is not None:
            self.title += data
        if self._in_h1 and self.h1:
            self.h1[-1] += data
        if self._in_jsonld and self.jsonld:
            self.jsonld[-1] += data

    def meta(self, key, value):
        for m in self.metas:
            if m.get(key) == value:
                return m.get("content", "")
        return None


def audit_page(base, path, findings):
    url = urljoin(base, path)
    status, body = fetch(url)
    if status != 200:
        findings.append((path, "FAIL", f"HTTP {status}"))
        return None, []
    p = PageParser()
    p.feed(body)

    def ok(cond, label, detail=""):
        findings.append((path, "ok" if cond else "FAIL",
                         f"{label}{': ' + detail if detail and not cond else ''}"))
        return cond

    # title
    t = (p.title or "").strip()
    ok(bool(t), "title present")
    if t:
        ok(10 <= len(t) <= 65, "title length 10-65", f"{len(t)} chars: {t!r}")
    # meta description
    d = p.meta("name", "description")
    ok(bool(d and d.strip()), "meta description present")
    if d:
        ok(50 <= len(d.strip()) <= 170, "description length 50-170", f"{len(d.strip())} chars")
    # canonical
    canon = [l.get("href") for l in p.links if "canonical" in str(l.get("rel", ""))]
    ok(len(canon) == 1, "exactly one canonical", f"found {len(canon)}")
    if canon:
        expected = url
        ok(canon[0].rstrip("/") == expected.rstrip("/") or canon[0] == expected,
           "canonical matches URL", f"canonical={canon[0]} url={expected}")
    # Open Graph
    for prop in ("og:title", "og:description", "og:url", "og:image", "og:type"):
        ok(bool(p.meta("property", prop)), f"{prop} present")
    ok(bool(p.meta("name", "twitter:card")), "twitter:card present")
    # feed discovery
    atom = [l.get("href") for l in p.links
            if "alternate" in str(l.get("rel", ""))
            and l.get("type") == "application/atom+xml"]
    ok(len(atom) == 1, "Atom feed link present", f"found {len(atom)}")
    # h1
    h1s = [h.strip() for h in p.h1 if h.strip()]
    ok(len(h1s) == 1, "exactly one h1", f"found {len(p.h1)}")
    # lang
    ok(bool(p.lang), "html lang present", "missing lang")
    # images alt
    for src, alt in p.imgs:
        ok(alt is not None, f"img alt present ({src[:60]})")
    # JSON-LD parses
    for i, block in enumerate(p.jsonld):
        try:
            json.loads(block)
            findings.append((path, "ok", f"JSON-LD block {i+1} parses"))
        except json.JSONDecodeError as e:
            findings.append((path, "FAIL", f"JSON-LD block {i+1} invalid: {e}"))
    # viewport + charset
    ok(bool(p.meta("name", "viewport")), "viewport meta present")
    ok('charset="utf-8"' in body.lower() or "charset=utf-8" in body.lower()
       or bool(re.search(r'<meta[^>]+charset', body, re.I)), "charset declared")
    # internal anchors for link check
    internal = []
    for href in p.anchors:
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        full = urljoin(url, href)
        if urlparse(full).netloc in ("mokhacaffe.com", "www.mokhacaffe.com"):
            internal.append(full.split("#")[0])
    return p, sorted(set(internal))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://mokhacaffe.com")
    args = ap.parse_args()
    base = args.base.rstrip("/") + "/"

    findings = []
    # discover pages from sitemap
    status, smap = fetch(urljoin(base, "sitemap.xml"))
    if status != 200:
        print(f"FAIL: sitemap.xml HTTP {status}")
        return 1
    smap_urls = re.findall(r"<loc>(.*?)</loc>", smap)
    paths = sorted({urlparse(u).path or "/" for u in smap_urls})
    print(f"sitemap.xml lists {len(smap_urls)} URLs -> {len(paths)} paths")

    all_internal = set()
    for path in paths:
        _, links = audit_page(base, path, findings)
        all_internal.update(links or [])

    # every sitemap URL should be https + apex
    for u in smap_urls:
        pr = urlparse(u)
        findings.append(("sitemap", "ok" if (pr.scheme == "https" and pr.netloc == "mokhacaffe.com")
                         else "FAIL", f"sitemap URL canonical form: {u}"))

    # Atom feed: reachable, well-formed, entries match sitemap pages
    ATOM = "{http://www.w3.org/2005/Atom}"
    fstatus, fbody = fetch(urljoin(base, "feed.xml"))
    findings.append(("feed", "ok" if fstatus == 200 else "FAIL",
                     f"feed.xml reachable: HTTP {fstatus}"))
    if fstatus == 200:
        try:
            import xml.etree.ElementTree as ET
            froot = ET.fromstring(fbody)
            entries = froot.findall(f"{ATOM}entry")
            findings.append(("feed", "ok" if froot.tag == f"{ATOM}feed" else "FAIL",
                             "feed.xml root is Atom <feed>"))
            findings.append(("feed", "ok" if len(entries) >= 1 else "FAIL",
                             f"feed has {len(entries)} entries"))
            for e in entries:
                for req in ("title", "id", "updated"):
                    if e.find(f"{ATOM}{req}") is None:
                        findings.append(("feed", "FAIL", f"entry missing <{req}>"))
                link = e.find(f"{ATOM}link")
                href = link.get("href", "") if link is not None else ""
                ep = urlparse(href).path
                findings.append(("feed", "ok" if ep in paths else "FAIL",
                                 f"entry URL in sitemap: {href}"))
        except Exception as ex:
            findings.append(("feed", "FAIL", f"feed.xml does not parse: {ex}"))

    # broken internal link check (GET each unique internal target once)
    checked = {}
    for link in sorted(all_internal):
        pr = urlparse(link)
        if pr.netloc == "www.mokhacaffe.com":
            findings.append(("links", "FAIL", f"internal link points at www host: {link}"))
            continue
        key = pr.path
        if key not in checked:
            st, _ = fetch(link)
            checked[key] = st
        if checked[key] != 200:
            findings.append(("links", "FAIL", f"broken internal link {link} -> HTTP {checked[key]}"))
    findings.append(("links", "ok", f"{len(all_internal)} unique internal links, "
                     f"{sum(1 for v in checked.values() if v == 200)}/{len(checked)} targets 200"))

    fails = [f for f in findings if f[1] == "FAIL"]
    for path, lvl, msg in findings:
        if lvl == "FAIL":
            print(f"[FAIL] {path}: {msg}")
    print(f"\n{len(findings)} checks, {len(fails)} FAIL "
          f"across {len(paths)} pages + sitemap + links")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
