"""Shared helpers: config loading, HTTP, text cleaning, time."""
from __future__ import annotations

import gzip
import html
import re
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UA = "Mozilla/5.0 (compatible; morning-news/1.0; +https://github.com/gusnil/morning-news)"


def load_yaml(path: Path | str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(path: Path | str | None = None) -> dict:
    cfg = load_yaml(path or ROOT / "feeds.yaml")
    cfg.setdefault("settings", {})
    cfg.setdefault("sections", [])
    cfg.setdefault("sources", [])
    return cfg


def active_sources(cfg: dict) -> list[dict]:
    """Sources the nightly build fetches: have a URL and are not dropped."""
    return [s for s in cfg["sources"] if s.get("url") and s.get("status") != "dropped"]


def http_get(url: str, timeout: float = 15, ua: str = DEFAULT_UA) -> tuple[int, bytes, str, str]:
    """GET a URL. Returns (status, body, final_url, content_type). Raises on network/HTTP errors."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, text/html;q=0.8, */*;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en,de;q=0.8,sv;q=0.6",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            body = gzip.decompress(body)
        elif enc == "deflate":
            try:
                body = zlib.decompress(body)
            except zlib.error:
                body = zlib.decompress(body, -zlib.MAX_WBITS)
        return resp.status, body, resp.geturl(), resp.headers.get("Content-Type", "")


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_text(s: str | None) -> str:
    """Strip HTML tags and entities, collapse whitespace."""
    if not s:
        return ""
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    return _WS.sub(" ", s).strip()


def rx(pattern: str | None):
    return re.compile(pattern, re.IGNORECASE) if pattern else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def local_tz(cfg: dict) -> ZoneInfo:
    return ZoneInfo(cfg.get("settings", {}).get("timezone", "Europe/Zurich"))
