"""Check every source in feeds.yaml and print a status table.

For each source:
  1. test the configured url (parseable feed, >= 1 item, newest item <= 30 days old);
  2. if that fails or url is null, try `candidates`, feeds advertised via
     <link rel="alternate" type="application/rss+xml|atom+xml"> on `homepage`
     and `discover_pages`, then common paths (/feed, /rss, /rss.xml, ...).

Usage:
  python build/validate_feeds.py [--only id,id] [--report feeds-status.md] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, http_get, load_config  # noqa: E402

MAX_AGE_DAYS = 30
COMMON_PATHS = ["/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml", "/news/rss", "/blog/feed/"]
LINK_TAG = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
A_HREF = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"']", re.IGNORECASE)
ATTR = re.compile(r"([a-zA-Z-]+)\s*=\s*([\"'])(.*?)\2", re.DOTALL)


def _err(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return f"network: {e.reason}"[:80]
    return f"{type(e).__name__}: {e}"[:80]


def check_feed(url: str, timeout: float, ua: str) -> dict:
    res = {"url": url, "ok": False, "items": 0, "newest": None, "error": None, "title": None}
    try:
        status, body, final, ctype = http_get(url, timeout, ua)
    except Exception as e:  # noqa: BLE001
        res["error"] = _err(e)
        return res
    res["final_url"] = final
    fp = feedparser.parse(body)
    entries = fp.entries or []
    if not entries:
        res["error"] = "not a feed" if "html" in ctype.lower() else "no items / unparseable"
        return res
    res["items"] = len(entries)
    res["title"] = (fp.feed.get("title") or "")[:60]
    dates = []
    for e in entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if t:
            dates.append(datetime(*t[:6], tzinfo=timezone.utc))
    if dates:
        now = datetime.now(timezone.utc)
        plausible = [d for d in dates if (d - now).days < 2] or dates
        newest = max(plausible)
        res["newest"] = newest.date().isoformat()
        age = (datetime.now(timezone.utc) - newest).days
        if age > MAX_AGE_DAYS:
            res["error"] = f"stale: newest item {age} days old"
            return res
    else:
        res["newest"] = "undated"
    res["ok"] = True
    return res


def discover_links(page_url: str, timeout: float, ua: str) -> tuple[list[str], str | None]:
    """Return feed URLs advertised on an HTML page (link rel=alternate first, then rss-looking anchors)."""
    try:
        _, body, final, _ = http_get(page_url, timeout, ua)
    except Exception as e:  # noqa: BLE001
        return [], _err(e)
    text = body.decode("utf-8", "replace")
    found: list[str] = []
    for tag in LINK_TAG.findall(text):
        attrs = {k.lower(): v for k, _, v in ATTR.findall(tag)}
        if "alternate" in attrs.get("rel", "").lower() and re.search(r"(rss|atom)\+xml", attrs.get("type", ""), re.I):
            if attrs.get("href"):
                found.append(urljoin(final, attrs["href"]))
    for href in A_HREF.findall(text):
        if re.search(r"(\brss\b|/feed\b|\.rss\b|rss\.xml|atom\.xml|/rss/|rss\.aspx|\?format=rss)", href, re.I):
            found.append(urljoin(final, href.replace("&amp;", "&")))
    seen, out = set(), []
    for u in found:
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:25], None


def validate_source(src: dict, timeout: float, ua: str) -> dict:
    tried: list[dict] = []
    row = {"id": src["id"], "name": src["name"], "section": src["section"], "configured": src.get("url"),
           "result": "dead", "working_url": None, "items": 0, "newest": None, "note": ""}

    def try_url(u: str) -> bool:
        if any(t["url"] == u for t in tried):
            return False
        r = check_feed(u, timeout, ua)
        tried.append(r)
        if r["ok"]:
            row.update(working_url=u, items=r["items"], newest=r["newest"])
            return True
        return False

    if src.get("url") and try_url(src["url"]):
        row["result"] = "ok"
    else:
        candidates = list(src.get("candidates") or [])
        disc_notes = []
        for page in [src.get("homepage")] + list(src.get("discover_pages") or []):
            if not page:
                continue
            links, err = discover_links(page, timeout, ua)
            if err:
                disc_notes.append(f"{urlsplit(page).netloc}{urlsplit(page).path} -> {err}")
            candidates += links
        base = src.get("homepage") or src.get("url")
        if base:
            p = urlsplit(base)
            candidates += [f"{p.scheme}://{p.netloc}{path}" for path in COMMON_PATHS]
        for u in candidates:
            if try_url(u):
                row["result"] = "fixed" if src.get("url") else "found"
                break
        if row["result"] == "dead":
            errs = sorted({t["error"] for t in tried if t["error"]})
            row["note"] = "; ".join(disc_notes + errs)[:300]
    if row["result"] != "ok" and tried and tried[0]["url"] == src.get("url"):
        row["note"] = (f"configured url: {tried[0]['error']}. " + row["note"]).strip()
    row["tried"] = tried
    return row


def to_markdown(rows: list[dict]) -> str:
    out = [
        f"Feed validation run {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
        f"(criteria: parseable, >= 1 item, newest <= {MAX_AGE_DAYS} days).",
        "",
        "| id | section | result | working URL | items | newest | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['id']} | {r['section']} | {r['result']} | {r['working_url'] or ''} | {r['items']} | "
            f"{r['newest'] or ''} | {r['note'].replace('|', '/')} |"
        )
    ok = sum(r["result"] != "dead" for r in rows)
    out += ["", f"{ok} of {len(rows)} sources have a working feed."]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "feeds.yaml"))
    ap.add_argument("--only", default="")
    ap.add_argument("--report")
    ap.add_argument("--json")
    ap.add_argument("--include-dropped", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    st = cfg["settings"]
    timeout, ua = float(st.get("fetch_timeout", 15)), st.get("user_agent")
    srcs = [s for s in cfg["sources"] if args.include_dropped or s.get("status") != "dropped"]
    if args.only:
        keep = set(args.only.split(","))
        srcs = [s for s in srcs if s["id"] in keep]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=int(st.get("fetch_workers", 8))) as pool:
        rows = list(pool.map(lambda s: validate_source(s, timeout, ua), srcs))
    md = to_markdown(rows)
    print(md)
    print(f"({time.time() - t0:.0f}s)")
    if args.report:
        Path(args.report).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
