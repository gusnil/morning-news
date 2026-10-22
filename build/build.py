"""Entry point: fetch -> cache -> cluster -> rank -> render.

  python build/build.py                # nightly build (fetches feeds)
  python build/build.py --no-fetch     # re-render from cache only (offline)

Exit code 1 (and no site written) when every feed fails.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config, local_tz, parse_iso  # noqa: E402
from fetch import enrich_images, fetch_all, load_cache, merge_cache, save_cache  # noqa: E402
from rank import build_sections, load_events  # noqa: E402
from render import render_site, snapshot_page  # noqa: E402

log = logging.getLogger("build")


def run(config: Path, cache_dir: Path, out_dir: Path, calendar: Path, now: datetime | None = None,
        fetch: bool = True, getter=None) -> dict:
    cfg = load_config(config)
    now = now or datetime.now(timezone.utc)
    tz = local_tz(cfg)
    local_day = now.astimezone(tz).date()
    st = cfg["settings"]
    items_path, pages_path = cache_dir / "items.json", cache_dir / "pages.json"

    items = load_cache(items_path)
    stats: dict = {"feeds_ok": None, "feeds_total": None, "failed": []}
    if fetch:
        kw = {"getter": getter} if getter else {}
        fresh, stats = fetch_all(cfg, now, **kw)
        log.info("feeds ok %s/%s, %d fresh items", stats["feeds_ok"], stats["feeds_total"], len(fresh))
        if stats["feeds_ok"] == 0:
            raise SystemExit("All feeds failed; not building or deploying.")
        items = merge_cache(items, fresh, now, int(st.get("cache_days", 7)))
        save_cache(items_path, items)

    sections = build_sections(cfg, items, now, local_day, load_events(calendar))
    if fetch:
        by_id = {it["id"]: it for it in items}
        shown = [by_id.get(c.item["id"], c.item) for sec in sections for g in sec["groups"] for c in g["cands"]]
        n = enrich_images(shown, cfg, **({"getter": getter} if getter else {}))
        for sec in sections:
            for g in sec["groups"]:
                for c in g["cands"]:
                    if c.item["id"] in by_id:
                        c.item["image"] = by_id[c.item["id"]].get("image", "")
        if n:
            log.info("og:image found for %d shown items", n)
        save_cache(items_path, items)
    page = snapshot_page(cfg, sections, now, local_day, tz, stats)

    pages = load_cache(pages_path) or {}
    if isinstance(pages, list):
        pages = {}
    if not fetch and local_day.isoformat() in pages:  # keep the real feed counts on an offline re-render
        page["feeds_ok"] = pages[local_day.isoformat()].get("feeds_ok")
        page["feeds_total"] = pages[local_day.isoformat()].get("feeds_total")
    pages[local_day.isoformat()] = page
    keep = sorted(pages, reverse=True)[: int(st.get("archive_days", 7))]
    pages = {d: pages[d] for d in sorted(keep)}
    pages_path.write_text(json.dumps(pages, ensure_ascii=False, indent=0), encoding="utf-8")

    render_site(pages, local_day.isoformat(), out_dir)
    for s in page["sections"]:
        log.info("%-6s %2d items%s", s["id"], s["count"], " (thin)" if s["thin"] else "")
    return {"page": page, "stats": stats}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "feeds.yaml"))
    ap.add_argument("--calendar", default=str(ROOT / "calendar.yaml"))
    ap.add_argument("--cache-dir", default=str(ROOT / "cache"))
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--no-fetch", action="store_true", help="render from cache only")
    ap.add_argument("--now", help="override build time (ISO 8601, for testing)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    now = parse_iso(args.now) if args.now else None
    res = run(Path(args.config), Path(args.cache_dir), Path(args.out), Path(args.calendar), now, not args.no_fetch)
    for sid, err in res["stats"]["failed"]:
        log.warning("source %s failed: %s", sid, err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
