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
ITEM_RE = re.compile(r"(?m)^[ \t]*(\d+)[.)][ \t]+(.+?)[ \t]*$")
DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{4}-\d{2}-\d{2})\.txt$")
SEPARATOR_RE = re.compile(r"(?m)^[ \t]*[=\-_*]{5,}[ \t]*$")

# Any ALL-CAPS line of 2+ words is a possible section heading...
HEADING_RE = re.compile(r"(?m)^[ \t]*([A-Z][A-Z0-9 &:,'’/\-]{2,}?)[ \t]*$")
# ...unless it is one of these structural lines.
RESERVED_RE = re.compile(
    r"(?i)(EDITOR['’]?S NOTE|WHAT TO WATCH(?: NEXT)?:?|SOURCES\s*&\s*VERIFICATION NOTE|.*\bBRIEFING\.?)"
)
WATCH_RE = re.compile(r"(?im)^[ \t]*WHAT TO WATCH(?: NEXT)?:?[ \t]*$")


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
    # If the site blocked the preview, build a readable title from the URL slug.
    if fallback["title"] == host:
        parts = [p for p in urlparse(url).path.split("/") if p.count("-") >= 3]
        if parts:
            slug = re.sub(r"[-_]?\d{4}-\d{2}-\d{2}$", "", max(parts, key=len))
            slug = re.sub(r"\.(html?|cms)$", "", slug).replace("-", " ").strip()
            if slug:
                fallback["title"] = slug[:1].upper() + slug[1:]
    return fallback


def cached_preview(url: str, cache: dict) -> dict:
    if url not in cache:
        cache[url] = get_preview(url)
        time.sleep(0.04)
    return cache[url]


def find_urls(text: str) -> list[str]:
    seen, urls = set(), []
    for raw in URL_RE.findall(text):
        url = raw.rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def extract_date(path: Path) -> str:
    match = DATE_RE.search(path.as_posix())
    if match:
        return match.group(3)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
    return match.group(1) if match else path.stem


def section_headings(text: str):
    """Return [(match, label)] for lines that look like section headings."""
    found = []
    for match in HEADING_RE.finditer(text):
        label = match.group(1).strip()
        if len(label.split()) < 2 or not re.search(r"[A-Z]{2}", label):
            continue
        if RESERVED_RE.fullmatch(label):
            continue
        found.append((match, label))
    return found


def strip_headings(text: str) -> str:
    for match, _ in reversed(section_headings(text)):
        text = text[:match.start()] + text[match.end():]
    return text


def section_info(label: str) -> tuple[str, str]:
    upper = label.upper()
    if upper.startswith("INDIA"):
        return "india", "India News"
    if upper.startswith(("GLOBAL", "WORLD", "INTERNATIONAL")):
        return "global", "Global News"
    key = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "section"
    title = re.sub(r"\bAi\b", "AI", label.title())
    return key, title


def parse_briefing(path: Path, preview_cache: dict) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    date = extract_date(path.relative_to(ROOT))
    coverage = re.search(r"(?im)^Coverage date:\s*(.+)$", text)
    prepared = re.search(r"(?im)^Prepared:\s*(.+)$", text)
    watch_match = WATCH_RE.search(text)
    before_watch = text[:watch_match.start()] if watch_match else text
    items = []
    matches = list(ITEM_RE.finditer(before_watch))
    # Track headings across the entire briefing, rather than searching only the
    # text between consecutive numbered headlines. This makes section assignment
    # reliable when a section heading follows the previous story's source block.
    headings = section_headings(before_watch)
    heading_index = 0
    current_key, current_title = "briefing", "More developments"
    for index, match in enumerate(matches):
        while heading_index < len(headings) and headings[heading_index][0].start() < match.start():
            current_key, current_title = section_info(headings[heading_index][1])
            heading_index += 1
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(before_watch)
        block = before_watch[match.end():block_end]
        urls = find_urls(block)
        clean = URL_RE.sub("", block)
        clean = SEPARATOR_RE.sub("", clean)
        clean = strip_headings(clean)
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
        items.append({
            "number": int(match.group(1)),
            "section": current_key,
            "section_title": current_title,
            "title": match.group(2).strip(),
            "summary": summary,
            "sources": [cached_preview(url, preview_cache) for url in urls],
        })

    what_to_watch = []
    if watch_match:
        tail = text[watch_match.end():]
        watch_end = re.search(r"(?im)^\s*(?:SOURCES\s*&\s*VERIFICATION NOTE|END OF BRIEFING\.?)\s*$", tail)
        watch_text = tail[:watch_end.start()] if watch_end else tail
        for line in watch_text.splitlines():
            stripped = line.strip()
            if re.match(r"^[-*•]\s+", stripped):
                value = re.sub(r"^[-*•]\s+", "", stripped).strip()
                if value and not re.fullmatch(r"[=\-_*]{5,}", value):
                    what_to_watch.append({"text": value, "sources": []})
            elif what_to_watch and URL_RE.search(stripped):
                for url in find_urls(stripped):
                    what_to_watch[-1]["sources"].append(cached_preview(url, preview_cache))

    # Editor's note (falls back to an old-style "Note:" line)
    editor = re.search(
        r"(?ims)^[ \t]*EDITOR['’]?S NOTE[ \t]*\n(.*?)(?=^[ \t]*[=\-_*]{5,}[ \t]*$|^[ \t]*[A-Z][A-Z0-9 &:,'’/\-]{2,}[ \t]*$|^[ \t]*\d+[.)][ \t]|\Z)",
        text,
    )
    editor_note = re.sub(r"\s+", " ", editor.group(1)).strip() if editor else next(
        (line.strip()[5:].strip() for line in text.splitlines() if line.strip().lower().startswith("note:")),
        "",
    )

    note_match = re.search(
        r"(?ims)^[ \t]*SOURCES\s*&\s*VERIFICATION NOTE[ \t]*\n(.*?)(?:^\s*END OF BRIEFING\.?\s*$|\Z)",
        text,
    )
    verification_note = ""
    if note_match:
        verification_note = re.sub(r"\s+", " ", note_match.group(1)).strip()
        verification_note = re.sub(r"^[=\-_* \t]+|[=\-_* \t]+$", "", verification_note)
    return {
        "date": date,
        "coverage": coverage.group(1).strip() if coverage else date,
        "prepared": prepared.group(1).strip() if prepared else "",
        "title": "AI & Tech Daily Briefing",
        "note": editor_note,
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