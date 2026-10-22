"""Scoring, caps and quotas (BRIEF §6).

score = source_weight + 1.5*ln(1 + n_sources) + boosts - penalties
        + 3 * 0.5^(age_hours/18) + event boost
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cluster import cluster  # noqa: E402
from common import load_yaml, rx  # noqa: E402
from fetch import item_time  # noqa: E402


# --------------------------------------------------------------------- calendar
def load_events(path: Path | str) -> list[dict]:
    try:
        data = load_yaml(path)
    except FileNotFoundError:
        return []
    return data.get("events", []) or []


def active_disciplines(events: list[dict], day: date, lag_days: int = 1) -> set[str]:
    """Disciplines with a boosting event on `day`. The 03:00 page reports the previous day,
    so a window stays active `lag_days` after the event's last day."""
    out = set()
    for ev in events:
        if ev.get("boost", True) is False:
            continue
        start, end = _d(ev["start"]), _d(ev.get("end") or ev["start"])
        if start <= day <= end + timedelta(days=lag_days):
            out.add(ev["discipline"])
    return out


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


# --------------------------------------------------------------------- candidates
@dataclass
class Cand:
    cl: dict
    score: float
    ts: float
    source: str
    source_name: str
    multi: bool
    regions: list[str] = field(default_factory=list)
    scope: str | None = None
    team: str | None = None
    sub: str | None = None
    text: str = ""

    @property
    def item(self) -> dict:
        return self.cl["canonical"]


def recency(age_hours: float) -> float:
    return 3 * 0.5 ** (max(age_hours, 0.0) / 18)


def keyword_delta(text: str, section: dict) -> float:
    d = 0.0
    for b in section.get("boost", []) or []:
        if rx(b["pattern"]).search(text):
            d += b["value"]
    for p in section.get("penalty", []) or []:
        if rx(p["pattern"]).search(text):
            d -= p["value"]
    return d


def score_cluster(cl: dict, src: dict, section: dict, now: datetime, events_on: set[str], event_boost: float) -> float:
    it = cl["canonical"]
    text = f"{it['title']} {it.get('excerpt', '')}"
    age_h = (now - item_time(it)).total_seconds() / 3600
    s = float(src.get("weight", 3))
    s += 1.5 * math.log(1 + len(cl["sources"]))
    s += keyword_delta(text, section)
    s += recency(age_h)
    if src.get("discipline") and src["discipline"] in events_on:
        s += event_boost
    return s


def make_cands(items, sources, section, now, events_on, event_boost) -> list[Cand]:
    weight_of = lambda sid: sources[sid].get("weight", 3)  # noqa: E731
    out = []
    for cl in cluster(items, weight_of):
        it = cl["canonical"]
        src = sources[it["source"]]
        region = src.get("region")
        out.append(Cand(
            cl=cl,
            score=score_cluster(cl, src, section, now, events_on, event_boost),
            ts=item_time(it).timestamp(),
            source=it["source"],
            source_name=src["name"],
            multi=len(cl["sources"]) > 1,
            regions=region if isinstance(region, list) else ([region] if region else []),
            scope=src.get("scope"),
            team=src.get("team"),
            sub=src.get("sub"),
            text=f"{it['title']} {it.get('excerpt', '')}",
        ))
    return out


def sort_key(c: Cand, multi_first: bool = False):
    return ((0 if c.multi else 1) if multi_first else 0, -round(c.score, 9), -c.ts, c.source_name, c.item["id"])


# --------------------------------------------------------------------- selection
def greedy(cands: list[Cand], n: int, ok=lambda c, chosen: True, chosen: list[Cand] | None = None,
           max_per_source: int = 3) -> list[Cand]:
    """Append up to n candidates from `cands` (already sorted) to `chosen`, respecting per-source max and `ok`."""
    chosen = chosen if chosen is not None else []
    added = 0
    for c in cands:
        if added >= n:
            break
        if c in chosen:
            continue
        if sum(1 for x in chosen if x.source == c.source) >= max_per_source:
            continue
        if not ok(c, chosen):
            continue
        chosen.append(c)
        added += 1
    return chosen


def select_world(cands: list[Cand], cap: int, quota: dict, max_per_source: int) -> list[Cand]:
    multi_first = quota.get("multi_source_first", True)
    ordered = sorted(cands, key=lambda c: sort_key(c, multi_first))
    region_max = max(1, math.floor(quota.get("region_max_share", 0.35) * cap))

    def ok(c, chosen):
        return all(sum(1 for x in chosen if r in x.regions) < region_max for r in c.regions)

    chosen: list[Cand] = []
    for req in quota.get("region_required", []):
        if any(req in x.regions for x in chosen):
            continue
        greedy([c for c in ordered if req in c.regions], 1, ok, chosen, max_per_source)
    greedy(ordered, cap - len(chosen), ok, chosen, max_per_source)
    return sorted(chosen, key=lambda c: sort_key(c, multi_first))


def select_basel(cands: list[Cand], cap: int, quota: dict, max_per_source: int) -> list[Cand]:
    ordered = sorted(cands, key=sort_key)
    local_scopes = set(quota.get("local_scopes", []))
    chosen = greedy([c for c in ordered if c.scope in local_scopes], quota.get("min_local", 6),
                    max_per_source=max_per_source)
    greedy(ordered, cap - len(chosen), chosen=chosen, max_per_source=max_per_source)
    return sorted(chosen, key=sort_key)


def select_simple(cands: list[Cand], cap: int, max_per_source: int) -> list[Cand]:
    return greedy(sorted(cands, key=sort_key), cap, max_per_source=max_per_source)


def sub_cap(sub: dict, day: date, events_on: set[str], sub_disciplines: set[str], bonus: int) -> int:
    cap = int(sub.get("cap_by_weekday", {}).get(day.weekday(), sub["cap"]))
    if sub_disciplines & events_on:
        cap = int(sub["event_cap"]) if "event_cap" in sub else cap + bonus
    return cap


def select_sport(cands: list[Cand], subs: list[dict], caps: dict[str, int], events_on: set[str],
                 sub_disciplines: dict[str, set[str]], max_per_source: int) -> dict[str, list[Cand]]:
    """Fill each sub-section to its cap, then release unused slots (teams -> cfb first, then anyone)."""
    by_sub = {s["id"]: sorted([c for c in cands if c.sub == s["id"]], key=sort_key) for s in subs}
    cfg = {s["id"]: s for s in subs}
    chosen: list[Cand] = []          # shared so max_per_source applies across the section
    picked: dict[str, list[Cand]] = {s["id"]: [] for s in subs}

    def rules_ok(c: Cand, ch: list[Cand]) -> bool:
        s = cfg[c.sub]
        if s.get("per_team") and c.team and sum(1 for x in ch if x.team == c.team) >= s["per_team"]:
            return False
        if "off_event_max" in s and not (sub_disciplines[c.sub] & events_on):
            req = rx(s.get("off_event_require"))
            if req and not req.search(c.text):
                return False
            if sum(1 for x in ch if x.sub == c.sub) >= s["off_event_max"]:
                return False
        return True

    def take(sid: str, n: int):
        pool = by_sub[sid]
        if cfg[sid].get("order") == "recent":
            pool = sorted(pool, key=lambda c: (-c.ts, c.source_name, c.item["id"]))
        before = len(chosen)
        greedy(pool, n, rules_ok, chosen, max_per_source)
        picked[sid].extend(chosen[before:])

    for s in subs:
        take(s["id"], caps[s["id"]])
    total_cap = sum(caps.values())
    # explicit release targets (teams -> cfb)
    for s in subs:
        unused = caps[s["id"]] - len(picked[s["id"]])
        for target in s.get("release_to", []):
            if unused <= 0:
                break
            n0 = len(picked[target])
            take(target, unused)
            unused -= len(picked[target]) - n0
    # anything still free goes to the best remaining candidate of any sub-section
    free = total_cap - len(chosen)
    if free > 0:
        rest = sorted([c for c in cands if c not in chosen], key=sort_key)
        before = len(chosen)
        greedy(rest, free, rules_ok, chosen, max_per_source)
        for c in chosen[before:]:
            picked[c.sub].append(c)
    for s in subs:
        if s.get("order") == "recent":
            picked[s["id"]].sort(key=lambda c: (-c.ts, c.source_name))
        else:
            picked[s["id"]].sort(key=sort_key)
    return picked


# --------------------------------------------------------------------- page
def build_sections(cfg: dict, items: list[dict], now: datetime, local_day: date, events: list[dict]) -> list[dict]:
    """Return [{id, title, groups: [{id, title, cands}], cap}] ready for rendering."""
    st = cfg["settings"]
    mps = int(st.get("max_per_source", 3))
    sources = {s["id"]: s for s in cfg["sources"]}
    events_on = active_disciplines(events, local_day)
    eb = float(cfg.get("event_boost", 2))
    bonus = int(cfg.get("event_cap_bonus", 2))
    out = []
    for sec in cfg["sections"]:
        def pool(window_h, sub=None):
            lo = now - timedelta(hours=window_h)
            return [it for it in items
                    if it["section"] == sec["id"] and it["source"] in sources
                    and sources[it["source"]].get("status") != "dropped"
                    and (sub is None or sources[it["source"]].get("sub") == sub)
                    and lo <= item_time(it) <= now + timedelta(hours=1)
                    and it["first_seen"] <= now.isoformat()]

        win = float(sec.get("window_hours", 36))
        if sec.get("subsections"):
            subs = sec["subsections"]
            cands = []
            for s in subs:
                cands += make_cands(pool(float(s.get("window_hours", win)), s["id"]), sources, sec, now, events_on, eb)
            sub_disc = {s["id"]: {src.get("discipline") for src in cfg["sources"]
                                  if src.get("sub") == s["id"] and src.get("discipline")} for s in subs}
            caps = {s["id"]: sub_cap(s, local_day, events_on, sub_disc[s["id"]], bonus) for s in subs}
            picked = select_sport(cands, subs, caps, events_on, sub_disc, mps)
            groups = [{"id": s["id"], "title": s["title"], "cands": picked[s["id"]]} for s in subs]
            cap = sum(caps.values())
        else:
            # Pinned sources (e.g. a company's own press releases) bypass ranking and caps: every item
            # from the last pin_window_hours is shown, newest first, in its own group below the section.
            pins = {sid for sid, s in sources.items() if s.get("section") == sec["id"] and s.get("pin")}
            main_pool = [it for it in pool(win) if it["source"] not in pins]
            pinned_group = None
            if pins:
                pw = float(sec.get("pin_window_hours", 26))
                pinned = make_cands([it for it in pool(pw) if it["source"] in pins], sources, sec, now, events_on, eb)
                pinned.sort(key=lambda c: (-c.ts, c.item["id"]))
                pinned_group = {"id": f"{sec['id']}-pinned", "title": sec.get("pin_title", "Pinned"),
                                "cands": pinned[: int(sec.get("pin_max", 6))]}
            cands = make_cands(main_pool, sources, sec, now, events_on, eb)
            cap = int(sec["cap"])
            q = sec.get("quota", {})
            if "region_max_share" in q:
                chosen = select_world(cands, cap, q, mps)
            elif "local_scopes" in q:
                chosen = select_basel(cands, cap, q, mps)
            else:
                chosen = select_simple(cands, cap, mps)
            groups = [{"id": sec["id"], "title": None, "cands": chosen}]
            if pinned_group and pinned_group["cands"]:
                groups.append(pinned_group)
                cap += len(pinned_group["cands"])
        out.append({"id": sec["id"], "title": sec["title"], "cap": cap, "groups": groups})
    return out
