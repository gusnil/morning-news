"""End-to-end: synthetic feeds through fetch -> cache -> rank -> render (no network)."""
import re
import subprocess
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import pytest

from build import run
from common import ROOT, active_sources, load_config

CFG = load_config()
URLS = sorted({s["url"] for s in active_sources(CFG)})
SHARED = "Earthquake of magnitude 7.1 strikes off coast of Japan, tsunami warning issued"
WORLD_SHARED = {s["url"] for s in active_sources(CFG) if s["id"] in ("france24", "aljazeera", "bbc")}

TEAM_WORDS = {"patriots": "Patriots", "celtics": "Celtics", "fcbasel": "FC Basel", "malmoff": "Malmö FF", "sweden": "Blågult landslaget"}
SUB_WORDS = {"cfb": "No. 3 Georgia playoff", "sumo": "yokozuna banzuke sumo", "cycling": "XCO World Cup"}


def fake_feed(url: str, now: datetime, dead: set[str]) -> bytes:
    if url in dead:
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    srcs = [s for s in CFG["sources"] if s.get("url") == url]
    hint = " ".join(TEAM_WORDS.get(s.get("team"), "") + " " + SUB_WORDS.get(s.get("sub"), "") for s in srcs)
    hint += " FCB Switzerland AI decision analytics"
    n = abs(hash(url)) % 1000
    items = []
    for i in range(8):
        title = SHARED if (url in WORLD_SHARED and i == 0) else f"{hint} story{n}x{i}d{now:%m%d} item"
        pub = format_datetime(now - timedelta(hours=i * 2 + 1))
        items.append(f"<item><title>{title}</title><link>{url}/a/{now:%m%d}/{i}</link>"
                     f"<description>Short excerpt {n}-{i}.</description><pubDate>{pub}</pubDate></item>")
    return f"<?xml version='1.0'?><rss version='2.0'><channel><title>x</title>{''.join(items)}</channel></rss>".encode()


def getter_for(now, dead=frozenset()):
    return lambda url, timeout, ua: (200, fake_feed(url, now, set(dead)), url, "application/rss+xml")


def night(tmp: Path, k: int, dead=frozenset()):
    now = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc) + timedelta(days=k)
    return run(ROOT / "feeds.yaml", tmp / "cache", tmp / "site", ROOT / "calendar.yaml", now, True, getter_for(now, dead))


@pytest.fixture
def tmp(tmp_path):
    (tmp_path / "cache").mkdir()
    return tmp_path


def test_full_build_page_contract(tmp):
    night(tmp, 0)
    html = (tmp / "site" / "index.html").read_text(encoding="utf-8")
    assert len(html.encode()) < 60_000
    assert f"{len(URLS)} of {len(URLS)} feeds OK" in html
    assert 'lang="de"' in html and 'lang="sv"' in html
    assert html.count(SHARED) == 1 and "also:" in html                      # clustered once with "also:"
    assert 'target="_blank" rel="noopener"' in html
    assert not re.search(r"<(img|iframe)\b|https?://[^\"]*\.(css|js)\b|fonts\.google", html)   # no external assets
    for sec in ("world", "basel", "sport", "chess", "ai"):
        assert f'id="{sec}"' in html
    assert (tmp / "site" / "style.css").exists() and (tmp / "site" / "app.js").stat().st_size < 3000


def test_twenty_percent_feeds_dead_still_builds_from_cache(tmp):
    night(tmp, 0)
    dead = set(URLS[:: 5])                                                    # every 5th feed = 20%
    res = night(tmp, 1, dead)
    html = (tmp / "site" / "index.html").read_text(encoding="utf-8")
    assert f"{len(URLS) - len(dead)} of {len(URLS)} feeds OK" in html
    for s in res["page"]["sections"]:
        assert s["count"] > 0, s["id"]
    dead_srcs = {s["name"] for s in active_sources(CFG) if s["url"] in dead}
    shown = {it["source"] for s in res["page"]["sections"] for g in s["groups"] for it in g["items"]}
    assert dead_srcs & shown, "items of failed feeds should still come from the cache"


def test_all_feeds_dead_fails_loudly_and_keeps_old_site(tmp):
    night(tmp, 0)
    before = (tmp / "site" / "index.html").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        night(tmp, 1, set(URLS))
    assert (tmp / "site" / "index.html").read_text(encoding="utf-8") == before


def test_archive_keeps_exactly_seven_days_after_eight_nights(tmp):
    for k in range(8):
        night(tmp, k)
    pages = sorted(p.name for p in (tmp / "site" / "archive").glob("2026-*.html"))
    assert len(pages) == 7 and pages[0] == "2026-10-21.html" and pages[-1] == "2026-10-27.html"
    assert "2026-10-27" in (tmp / "site" / "archive" / "index.html").read_text(encoding="utf-8")


def test_caps_hold_on_rendered_page(tmp):
    res = night(tmp, 0)
    caps = {s["id"]: s.get("cap") for s in CFG["sections"]}
    for s in res["page"]["sections"]:
        if caps[s["id"]]:
            assert s["count"] <= caps[s["id"]]
        names = [it["source"] for g in s["groups"] for it in g["items"]]
        assert all(names.count(n) <= 3 for n in set(names)) or s["id"] == "sport"


def test_no_ai_in_build_code():
    out = subprocess.run(["grep", "-ri", r"openai\|anthropic\|deepl\|translate\|embedding", str(ROOT / "build")],
                         capture_output=True, text=True)
    assert out.stdout == ""
