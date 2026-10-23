"""Render page snapshots to static HTML with Jinja2."""
from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cluster import tokens  # noqa: E402
from common import ROOT, parse_iso  # noqa: E402
from fetch import item_time  # noqa: E402

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def show_excerpt(title: str, excerpt: str, max_len: int) -> str:
    """Excerpt only if <= max_len chars and not a repeat of the headline."""
    if not excerpt or len(excerpt) > max_len:
        return ""
    t, e = tokens(title), tokens(excerpt)
    if not e or (t and len(t & e) / len(t | e) >= 0.6):
        return ""
    tl, el = title.lower().strip(" .…"), excerpt.lower().strip(" .…")
    if el.startswith(tl) or tl.startswith(el):
        return ""
    return excerpt


def snapshot_item(cand, sources: dict, tz, local_day: date, excerpt_max: int) -> dict:
    it = cand.item
    t = item_time(it).astimezone(tz)
    when = t.strftime("%H:%M") if t.date() == local_day else f"{WEEKDAYS[t.weekday()]} {t:%H:%M}"
    own = sources[it["source"]]["name"]
    also = []
    for sid in cand.cl["also"]:
        n = sources[sid]["name"] if sid in sources else sid
        if n != own and n not in also:
            also.append(n)
    return {
        "id": it["id"],
        "title": it["title"],
        "url": it["url"],
        "source": own,
        "when": when,
        "also": also,
        "lang": it.get("lang", "en"),
        "image": it.get("image") or None,
        "excerpt": show_excerpt(it["title"], it.get("excerpt", ""), excerpt_max),
    }


def edition(local_hour: int) -> str:
    """Name of the edition a build belongs to (late GitHub starts stay in their edition)."""
    return "Morning" if local_hour < 10 else "Midday" if local_hour < 16 else "Evening"


def snapshot_page(cfg: dict, sections: list[dict], now: datetime, local_day: date, tz, stats: dict) -> dict:
    sources = {s["id"]: s for s in cfg["sources"]}
    st = cfg["settings"]
    thin = int(st.get("thin_threshold", 4))
    emax = int(st.get("excerpt_max", 160))
    out_secs = []
    for sec in sections:
        groups = [{"id": g["id"], "title": g["title"],
                   "items": [snapshot_item(c, sources, tz, local_day, emax) for c in g["cands"]]}
                  for g in sec["groups"]]
        n = sum(len(g["items"]) for g in groups)
        flat = [it for g in groups for it in g["items"]]
        # Lead story: the best-ranked of the top three that has a picture; else simply the top story.
        lead = next((it for it in flat[:3] if it["image"]), flat[0] if flat else None)
        out_secs.append({"id": sec["id"], "title": sec["title"], "count": n, "thin": n < thin, "groups": groups,
                         "lead": lead["id"] if lead else None})
    return {
        "date": local_day.isoformat(),
        "built_at": now.isoformat(),
        "built_local": now.astimezone(tz).strftime("%H:%M"),
        "edition": edition(now.astimezone(tz).hour),
        "feeds_ok": stats.get("feeds_ok"),
        "feeds_total": stats.get("feeds_total"),
        "sections": out_secs,
    }


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    env.filters["longdate"] = lambda d: (lambda x: f"{days[x.weekday()]} {x.day} {months[x.month - 1]} {x.year}")(date.fromisoformat(d))
    env.filters["nicedate"] = lambda d: f"{WEEKDAYS[date.fromisoformat(d).weekday()]} {date.fromisoformat(d):%d.%m.%Y}"
    return env


def render_site(pages: dict[str, dict], today: str, out_dir: Path | str) -> list[Path]:
    """Write index.html (today), archive/<date>.html for every snapshot, archive/index.html, static files."""
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "archive").mkdir(parents=True)
    env = _env()
    dates = sorted(pages, reverse=True)
    written = []

    def write(path: Path, html: str):
        path.write_text(html, encoding="utf-8")
        written.append(path)

    tpl = env.get_template("index.html")
    write(out / "index.html", tpl.render(page=pages[today], root="", is_archive=False, dates=dates))
    for d in dates:
        write(out / "archive" / f"{d}.html", tpl.render(page=pages[d], root="../", is_archive=True, dates=dates))
    write(out / "archive" / "index.html",
          env.get_template("archive.html").render(pages=[pages[d] for d in dates], root="../", today=today))
    for f in ("style.css", "app.js"):
        shutil.copy(ROOT / "static" / f, out / f)
    return written
