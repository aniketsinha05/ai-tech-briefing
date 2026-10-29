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
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AI-Tech-Briefing/1.0)",
                "Accept": "text/html",
            },
        )
        with urlopen(req, timeout=5) as response:
            if "text/html" not in response.headers.get("Content-Type", "").lower():
                return fallback
            raw = response.read(180_000).decode("utf-8", "replace")
        parser = MetaParser()
        parser.feed(raw)
        title = (
            parser.meta.get("og:title")
            or parser.meta.get("twitter:title")
            or " ".join(parser.title_parts)
        ).strip()
        description = (
            parser.meta.get("og:description")
            or parser.meta.get("description")
            or parser.meta.get("twitter:description")
            or ""
        ).strip()
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
    coverage = re.search(r"(?im)^Coverage date:\s*(.+)$", text)
    prepared = re.search(r"(?im)^Prepared:\s*(.+)$", text)
    watch_match = re.search(r"(?im)^\s*WHAT TO WATCH\s*$", text)
    before_watch = text[:watch_match.start()] if watch_match else text
    items = []
    matches = list(ITEM_RE.finditer(before_watch))
    current_section = "BRIEFING"
    section_pattern = re.compile(r"(?im)^\s*(INDIA\s*:\s*AI\s*&\s*TECH|GLOBAL\s+AI\s*(?:&|AND)\s*TECH(?:NOLOGY)?|GLOBAL\s+AI\s*&\s*TECHNOLOGY)\s*$")
    section_matches = list(section_pattern.finditer(before_watch))
    for index, match in enumerate(matches):
        previous_text_start = matches[index - 1].end() if index else 0
        prefix = before_watch[previous_text_start:match.start()]
        detected = list(section_pattern.finditer(prefix))
        if detected:
            label = detected[-1].group(1).upper()
            current_section = "INDIA" if label.startswith("INDIA") else "GLOBAL"
        start_block = match.end()
        end_block = matches[index + 1].start() if index + 1 < len(matches) else len(before_watch)
        block = before_watch[start_block:end_block]
        urls = URL_RE.findall(block)
        clean = URL_RE.sub("", block)
        clean = re.sub(r"(?im)^\s*(?:Source|Sources|Related research update):\s*$", "", clean)
        paragraphs = [
            re.sub(r"\s+", " ", paragraph).strip()
            for paragraph in re.split(r"\n\s*\n", clean)
            if paragraph.strip()
        ]
        summary = " ".join(
            paragraph for paragraph in paragraphs
            if not re.match(r"(?i)^(?:Source|Sources|Related research update):", paragraph)
            and not re.fullmatch(r"[=\-_*]{5,}", paragraph.strip())
        )
        previews = []
        for url in urls:
            if url not in preview_cache:
                preview_cache[url] = get_preview(url)
                time.sleep(0.04)
            previews.append(preview_cache[url])
        items.append({
            "number": int(match.group(1)),
            "section": current_section,
            "title": match.group(2).strip(),
            "summary": summary,
            "sources": previews,
        })
    what_to_watch = []
    if watch_match:
        watch_end = re.search(r"(?im)^\s*(?:SOURCES\s*&\s*VERIFICATION NOTE|END OF BRIEFING|END OF BRIEFING\.)\s*$", text[watch_match.end():])
        watch_text = text[watch_match.end():watch_match.end() + watch_end.start()] if watch_end else text[watch_match.end():]
        for line in watch_text.splitlines():
            stripped = line.strip()
            if re.match(r"^[-*•]\s+", stripped):
                value = re.sub(r"^[-*•]\s+", "", stripped).strip()
                if value and not re.fullmatch(r"[=\-_*]{5,}", value):
                    what_to_watch.append(value)
    note_match = re.search(r"(?ims)^SOURCES\s*&\s*VERIFICATION NOTE\s*\n(.*?)(?:^\s*END OF BRIEFING\.?\s*$|\Z)", text)
    verification_note = ""
    if note_match:
        verification_note = re.sub(r"\s+", " ", note_match.group(1)).strip()
        verification_note = re.sub(r"^[=\-_*\s]+|[=\-_*\s]+$", "", verification_note)
    return {
        "date": date,
        "coverage": coverage.group(1).strip() if coverage else date,
        "prepared": prepared.group(1).strip() if prepared else "",
        "title": "AI & Tech Daily Briefing",
        "note": next(
            (line.strip()[5:].strip() for line in text.splitlines() if line.strip().lower().startswith("note:")),
            "",
        ),
        "items": items,
        "what_to_watch": what_to_watch,
        "verification_note": verification_note,
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
    (DIST / "briefings.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8"
    )
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built site with {len(entries)} briefing(s) and {len(preview_cache)} source preview(s).")


if __name__ == "__main__":
    main()
