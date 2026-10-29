#!/usr/bin/env python3
"""Build a static, searchable site from dated plain-text briefing files."""
from __future__ import annotations

import html
import json
import re
import shutil
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BRIEFINGS = ROOT / "ai-tech-briefing"
SITE = ROOT / "site"
DIST = ROOT / "dist"
URL_RE = re.compile(r"https?://[^\s<>\"')]+")
ITEM_RE = re.compile(r"(?m)^\s*(\d+)\.\s+(.+?)\s*$")
DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{4}-\d{2}-\d{2})\.txt$")

class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts = []
        self.in_title = False
        self.meta = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            value = attrs.get("content", "").strip()
            if key and value:
                self.meta[key] = value
    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False
    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data.strip())

def get_preview(url: str) -> dict:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    fallback = {"url": url, "domain": host, "title": host or url, "description": ""}
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Tech-Briefing/1.0)", "Accept": "text/html"})
        with urlopen(req, timeout=5) as response:
            if "text/html" not in response.headers.get("Content-Type", "").lower():
                return fallback
            raw = response.read(180_000).decode("utf-8", "replace")
        parser = MetaParser()
        parser.feed(raw)
        title = (parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.title_parts)).strip()
        description = (parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description") or "").strip()
        fallback["title"] = html.unescape(title)[:180] if title else fallback["title"]
        fallback["description"] = html.unescape(description)[:260]
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        pass
    return fallback

def extract_date(path: Path) -> str:
    match = DATE_RE.search(path.as_posix())
    if match:
        return match.group(3)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
    return match.group(1) if match else path.stem

def parse_briefing(path: Path, preview_cache: dict) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    date = extract_date(path.relative_to(ROOT))
    title_match = re.search(r"(?im)^AI\s*&\s*TECH DAILY BRIEFING\s*$", text)
    coverage = re.search(r"(?im)^Coverage date:\s*(.+)$", text)
    prepared = re.search(r"(?im)^Prepared:\s*(.+)$", text)
    items = []
    matches = list(ITEM_RE.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        urls = URL_RE.findall(block)
        clean = URL_RE.sub("", block)
        clean = re.sub(r"(?im)^\s*(?:Source|Related research update):\s*$", "", clean)
        clean = re.sub(r"(?m)^\s*[-*]\s+", "", clean)
        paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
        summary = " ".join(p for p in paragraphs if not re.match(r"(?i)^(?:Source|Related research update):", p))
        previews = []
        for url in urls:
            if url not in preview_cache:
                preview_cache[url] = get_preview(url)
                time.sleep(0.08)
            previews.append(preview_cache[url])
        items.append({"number": int(match.group(1)), "title": match.group(2).strip(), "summary": summary, "sources": previews})
    what_to_watch = []
    watch = re.search(r"(?is)WHAT TO WATCH\s*\n(.*?)(?:\n\s*END OF BRIEFING|$)", text)
    if watch:
        what_to_watch = [re.sub(r"^\s*[-*]\s*", "", line).strip() for line in watch.group(1).splitlines() if line.strip()]
    return {
        "date": date,
        "coverage": coverage.group(1).strip() if coverage else date,
        "prepared": prepared.group(1).strip() if prepared else "",
        "title": "AI & Tech Daily Briefing",
        "note": next((line.strip() for line in text.splitlines() if line.strip().lower().startswith("note:")), ""),
        "items": items,
        "what_to_watch": what_to_watch,
        "raw_text": text,
        "path": path.relative_to(ROOT).as_posix(),
    }

def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    for asset in ("index.html", "styles.css", "app.js"):
        shutil.copy2(SITE / asset, DIST / asset)
    files = sorted(BRIEFINGS.rglob("*.txt"), reverse=True) if BRIEFINGS.exists() else []
    preview_cache = {}
    entries = [parse_briefing(path, preview_cache) for path in files]
    entries.sort(key=lambda entry: entry["date"], reverse=True)
    (DIST / "briefings.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built site with {len(entries)} briefing(s) and {len(preview_cache)} source preview(s).")

if __name__ == "__main__":
    main()
