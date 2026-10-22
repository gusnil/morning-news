"""Fetch every active feed, normalise entries, merge into the 7-day cache."""
from __future__ import annotations

import hashlib
import json
import html as _html
import logging
import re
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


_IMG = re.compile(r"<img[^>]+?src=[\"']([^\"']+)", re.I)
_JUNK = re.compile(r"pixel|tracking|1x1|spacer|gravatar|emoji|feedburner|/ads?/|blank\.gif|logo", re.I)


def clean_image(url: str | None, base: str = "") -> str | None:
    """Return a usable https image URL or None."""
    if not url:
        return None
    from urllib.parse import urljoin
    u = urljoin(base, _html.unescape(str(url).strip()))
    if u.startswith("http://"):
        u = "https://" + u[7:]
    if not u.startswith("https://") or len(u) > 1000 or _JUNK.search(u):
        return None
    return u


def entry_image(e, base: str = "") -> str | None:
    """Best image for a feed entry: media:content > media:thumbnail > enclosure > first <img> in the body."""
    media = []
    for m in e.get("media_content") or []:
        t, med = str(m.get("type") or ""), str(m.get("medium") or "")
        if m.get("url") and (med == "image" or t.startswith("image") or (not t and not med)):
            try:
                w = int(m.get("width") or 0)
            except (TypeError, ValueError):
                w = 0
            media.append((w, m["url"]))
    if media:
        big = [m for m in media if m[0] >= 480]
        return clean_image(min(big)[1] if big else max(media)[1], base)
    for m in e.get("media_thumbnail") or []:
        if clean_image(m.get("url"), base):
            return clean_image(m.get("url"), base)
    for l in list(e.get("enclosures") or []) + [l for l in e.get("links") or [] if l.get("rel") == "enclosure"]:
        if str(l.get("type") or "").startswith("image") and clean_image(l.get("href") or l.get("url"), base):
            return clean_image(l.get("href") or l.get("url"), base)
    body = " ".join([str(e.get("summary") or "")] + [str(c.get("value") or "") for c in e.get("content") or []])
    for m in _IMG.finditer(body):
        if clean_image(m.group(1), base):
            return clean_image(m.group(1), base)
    return None


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
        rec = {
            "id": item_id(src["id"], url),
            "url": url,
            "title": title,
            "excerpt": excerpt,
            "source": src["id"],
            "section": src["section"],
            "published": iso(pub) if pub else None,
            "first_seen": iso(now),
            "lang": src.get("lang", "en"),
        }
        img = entry_image(e, url)
        if img:
            rec["image"] = img
        out.append(rec)
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
            if "image" not in it and "image" in old:   # keep an og:image found (or tried) on an earlier night
                it["image"] = old["image"]
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


_OG = [re.compile(p, re.I) for p in (
    r"<meta[^>]+property=[\"']og:image(?::secure_url|:url)?[\"'][^>]*content=[\"']([^\"']+)",
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*property=[\"']og:image(?::secure_url|:url)?[\"']",
    r"<meta[^>]+name=[\"']twitter:image(?::src)?[\"'][^>]*content=[\"']([^\"']+)",
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*name=[\"']twitter:image(?::src)?[\"']",
)]


def og_image(html_text: str, base: str) -> str | None:
    head = html_text[:300_000]
    for rx_ in _OG:
        m = rx_.search(head)
        if m and clean_image(m.group(1), base):
            return clean_image(m.group(1), base)
    return None


def enrich_images(items: list[dict], cfg: dict, getter=http_get) -> int:
    """For shown items whose feed had no image, read the article's og:image once.
    Stores "" when none is found so the page is not fetched again on later nights."""
    todo = [it for it in items if "image" not in it]
    if not todo:
        return 0
    st = cfg["settings"]
    ua = st.get("user_agent")

    def get(it):
        try:
            _, body, final, _ = getter(it["url"], 8.0, ua)
            return it, og_image(body.decode("utf-8", "replace"), final or it["url"]) or ""
        except Exception:  # noqa: BLE001
            return it, ""

    found = 0
    with ThreadPoolExecutor(max_workers=int(st.get("fetch_workers", 8))) as pool:
        for it, img in pool.map(get, todo):
            it["image"] = img
            found += bool(img)
    return found
