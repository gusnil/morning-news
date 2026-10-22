"""Fetch every active feed, normalise entries, merge into the 7-day cache."""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import active_sources, clean_text, http_get, iso, parse_iso, rx  # noqa: E402

log = logging.getLogger("fetch")
EXCERPT_STORE = 300  # chars kept in cache; render decides what to show
TRACKING = ("utm_", "at_", "ito", "cmpid", "ref", "xtor", "sr_share", "fbclid", "gclid")


def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith(TRACKING)]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(q), ""))


def item_id(source_id: str, url: str) -> str:
    return hashlib.sha1(f"{source_id}|{canonical_url(url)}".encode()).hexdigest()[:16]


def _entry_time(e) -> datetime | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def passes_filters(src: dict, text: str) -> bool:
    inc, req, exc = rx(src.get("include")), rx(src.get("require")), rx(src.get("exclude"))
    if inc and not inc.search(text):
        return False
    if req and not req.search(text):
        return False
    if exc and exc.search(text):
        return False
    return True


def normalise(src: dict, entries, now: datetime) -> list[dict]:
    out = []
    for e in entries:
        url = e.get("link") or e.get("id")
        title = clean_text(e.get("title"))
        if not url or not title or not str(url).startswith("http"):
            continue
        excerpt = clean_text(e.get("summary") or e.get("description"))[:EXCERPT_STORE]
        if not passes_filters(src, f"{title} {excerpt}"):
            continue
        pub = _entry_time(e)
        if pub is None or pub > now + timedelta(hours=1):
            pub = None  # undated or bogus future date: fall back to first_seen
        out.append({
            "id": item_id(src["id"], url),
            "url": url,
            "title": title,
            "excerpt": excerpt,
            "source": src["id"],
            "section": src["section"],
            "published": iso(pub) if pub else None,
            "first_seen": iso(now),
            "lang": src.get("lang", "en"),
        })
    return out


def fetch_all(cfg: dict, now: datetime | None = None, getter=http_get) -> tuple[list[dict], dict]:
    """Fetch all active sources. Returns (items, stats). Each distinct URL is fetched once."""
    now = now or datetime.now(timezone.utc)
    st = cfg["settings"]
    timeout, ua = float(st.get("fetch_timeout", 15)), st.get("user_agent")
    srcs = active_sources(cfg)
    urls = sorted({s["url"] for s in srcs})

    def get(url):
        try:
            _, body, _, _ = getter(url, timeout, ua)
            fp = feedparser.parse(body)
            if not fp.entries:
                raise ValueError("no entries / parse error")
            return url, fp.entries, None
        except Exception as e:  # noqa: BLE001
            return url, None, f"{type(e).__name__}: {e}"[:120]

    with ThreadPoolExecutor(max_workers=int(st.get("fetch_workers", 8))) as pool:
        results = {u: (ents, err) for u, ents, err in pool.map(get, urls)}

    items, failed = [], []
    for src in srcs:
        ents, err = results[src["url"]]
        if err:
            failed.append((src["id"], err))
            continue
        items.extend(normalise(src, ents, now))
    bad_urls = [u for u, (_, err) in results.items() if err]
    for u in bad_urls:
        log.warning("feed failed: %s (%s)", u, results[u][1])
    stats = {"feeds_total": len(urls), "feeds_ok": len(urls) - len(bad_urls), "failed": failed}
    return items, stats


def load_cache(path: Path) -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def merge_cache(cached: list[dict], fresh: list[dict], now: datetime, keep_days: int = 7) -> list[dict]:
    """Union by id. Keeps the earliest first_seen; refreshes title/excerpt. Drops items older than keep_days."""
    by_id = {c["id"]: c for c in cached}
    for it in fresh:
        old = by_id.get(it["id"])
        if old:
            it = {**it, "first_seen": old["first_seen"], "published": it["published"] or old.get("published")}
        by_id[it["id"]] = it
    cutoff = now - timedelta(days=keep_days)
    kept = [it for it in by_id.values() if item_time(it) >= cutoff]
    kept.sort(key=lambda x: (x["section"], item_time(x), x["id"]), reverse=True)
    return kept


def item_time(it: dict) -> datetime:
    return parse_iso(it.get("published")) or parse_iso(it["first_seen"])


def save_cache(path: Path, items: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(items, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
