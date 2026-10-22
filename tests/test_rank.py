import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from rank import active_disciplines, build_sections, recency

NOW = datetime(2026, 10, 22, 1, 0, tzinfo=timezone.utc)   # 03:00 Zurich, a Thursday
DAY = date(2026, 10, 22)


def src(id, section, weight=3, **kw):
    return {"id": id, "name": id.upper(), "section": section, "weight": weight, "lang": "en", "url": f"https://{id}", **kw}


CFG = {
    "settings": {"max_per_source": 3, "thin_threshold": 4},
    "event_boost": 2, "event_cap_bonus": 2,
    "sections": [
        {"id": "world", "title": "World", "cap": 10, "window_hours": 36,
         "quota": {"region_max_share": 0.35, "region_required": ["ASIA", "AFR", "LATAM", "ME"], "multi_source_first": True}},
        {"id": "basel", "title": "Basel", "cap": 10, "window_hours": 36,
         "quota": {"local_scopes": ["Basel", "BL", "Local"], "min_local": 6}},
        {"id": "sport", "title": "Sport", "window_hours": 36, "subsections": [
            {"id": "cycling", "title": "Cycling", "cap": 4},
            {"id": "teams", "title": "Teams", "cap": 6, "per_team": 1, "order": "recent", "release_to": ["cfb"]},
            {"id": "cfb", "title": "College football", "cap": 1, "cap_by_weekday": {6: 2, 0: 2}},
            {"id": "sumo", "title": "Sumo", "cap": 1, "event_cap": 2, "off_event_max": 1,
             "off_event_require": "banzuke|promot|retire|yokozuna|ozeki"},
        ]},
        {"id": "chess", "title": "Chess", "cap": 8, "window_hours": 48,
         "boost": [{"value": 1, "pattern": "Candidates"}], "penalty": [{"value": 2, "pattern": "puzzle"}]},
    ],
    "sources": [
        src("eu1", "world", 5, region="EU"), src("eu2", "world", 4, region="EU"), src("eu3", "world", 4, region="EU"),
        src("eu4", "world", 3, region="EU"), src("me", "world", 4, region="ME"), src("asia", "world", 4, region="ASIA"),
        src("afr", "world", 4, region="AFR"), src("latam", "world", 3, region="LATAM"), src("us", "world", 5, region="US"),
        src("bs1", "basel", 5, scope="Basel"), src("bs2", "basel", 4, scope="Basel"), src("bs3", "basel", 3, scope="BL"),
        src("ch1", "basel", 5, scope="CH"), src("ch2", "basel", 5, scope="CH"),
        src("cyc1", "sport", 5, sub="cycling", discipline="cycling"), src("cyc2", "sport", 4, sub="cycling", discipline="cycling"),
        src("pats", "sport", 3, sub="teams", team="patriots"), src("sox", "sport", 3, sub="teams", team="redsox"),
        src("cfb", "sport", 3, sub="cfb", discipline="cfb"), src("sumo", "sport", 4, sub="sumo", discipline="sumo"),
        src("chessA", "chess", 5), src("chessB", "chess", 3),
    ],
}

_n = [0]


def it(source, title, hours_ago=2.0, section=None):
    _n[0] += 1
    s = next(x for x in CFG["sources"] if x["id"] == source)
    t = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"id": f"i{_n[0]}", "source": source, "section": section or s["section"], "title": title,
            "excerpt": "", "url": f"https://{source}/{_n[0]}", "published": t, "first_seen": t, "lang": "en"}


WORDS = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa quebec romeo sierra tango".split()


def uniq(k):
    """A title sharing no tokens with uniq(j) for j != k."""
    return f"{WORDS[k % 20]}{k} {WORDS[(k * 7 + 3) % 20]}x{k} story{k}"


def sections(items, cfg=CFG, now=NOW, day=DAY, events=()):
    return {s["id"]: s for s in build_sections(cfg, items, now, day, list(events))}


def flat(sec):
    return [c for g in sec["groups"] for c in g["cands"]]


def test_recency_halves_every_18h():
    assert recency(0) == 3 and math.isclose(recency(18), 1.5) and math.isclose(recency(36), 0.75)


def test_world_region_cap_required_regions_and_source_cap():
    items = [it(s, uniq(i + 10 * k)) for k, s in enumerate(["eu1", "eu2", "eu3", "eu4", "us"]) for i in range(6)]
    items += [it("me", uniq(100 + i), 20) for i in range(4)]
    items += [it("asia", uniq(120 + i), 20) for i in range(4)]
    items += [it("afr", uniq(140), 30), it("latam", uniq(160), 30)]
    chosen = flat(sections(items)["world"])
    assert len(chosen) == 10
    regions = Counter(r for c in chosen for r in c.regions)
    assert max(regions.values()) <= math.floor(0.35 * 10)
    for req in ("ASIA", "AFR", "LATAM", "ME"):
        assert regions[req] >= 1
    assert max(Counter(c.source for c in chosen).values()) <= 3


def test_world_multi_source_clusters_rank_above_singles():
    items = [it("eu1", uniq(i), 0.1) for i in range(3)]                       # fresh, weight 5, single-source
    items += [it("latam", "Volcano erupts near Guatemala City", 30), it("afr", "Volcano erupts near Guatemala City as ash spreads", 30)]
    chosen = flat(sections(items)["world"])
    assert chosen[0].multi and "also" in chosen[0].cl and chosen[0].cl["also"]


def test_basel_six_local_before_national():
    items = [it(s, uniq(200 + 10 * k + i)) for k, s in enumerate(["ch1", "ch2"]) for i in range(5)]
    items += [it(s, uniq(300 + 10 * k + i), 10) for k, s in enumerate(["bs1", "bs2", "bs3"]) for i in range(3)]
    chosen = flat(sections(items)["basel"])
    assert len(chosen) == 10
    assert sum(c.scope in ("Basel", "BL", "Local") for c in chosen) >= 6
    assert max(Counter(c.source for c in chosen).values()) <= 3


def test_sport_caps_per_team_and_release_to_cfb():
    items = [it("cyc1", uniq(400 + i)) for i in range(5)] + [it("cyc2", uniq(410 + i)) for i in range(5)]
    items += [it("pats", uniq(420 + i), 1 + i) for i in range(4)] + [it("sox", uniq(430 + i), 3 + i) for i in range(4)]
    items += [it("cfb", f"No. {i + 1} team wins {uniq(440 + i)}") for i in range(6)]
    sport = sections(items)["sport"]
    g = {x["id"]: x["cands"] for x in sport["groups"]}
    assert len(g["teams"]) == 2 and {c.team for c in g["teams"]} == {"patriots", "redsox"}   # max 1 per team
    assert g["teams"][0].team == "patriots"                                                      # most recent first
    assert len(g["cfb"]) == 3   # own slot (cap 1) + 2 of the 4 freed team slots (cfb source hits max 3)
    assert len(g["cycling"]) == 6   # remaining freed slots (teams + unused sumo) go to the best leftovers
    assert sum(len(v) for v in g.values()) <= sport["cap"] == 12
    assert max(Counter(c.source for c in flat(sport)).values()) <= 3


def test_cfb_cap_two_on_sunday_and_monday():
    items = [it("cfb", f"No. {i + 1} {uniq(500 + i)}") for i in range(3)]
    items += [it("pats", uniq(510 + i)) for i in range(1)]
    cfg = {**CFG, "sections": [s for s in CFG["sections"] if s["id"] == "sport"]}
    sun = datetime(2026, 10, 25, 2, 0, tzinfo=timezone.utc)
    thu = sections(items, cfg)["sport"]
    sunday = sections(items, cfg, now=sun + timedelta(hours=0), day=date(2026, 10, 25))["sport"]
    assert thu["cap"] == 12 and sunday["cap"] == 13


def test_sumo_outside_basho_needs_keyword_and_max_one():
    items = [it("sumo", "Kyushu basho preview " + uniq(600)), it("sumo", "New banzuke released " + uniq(601)),
             it("sumo", "Ozeki promotion talk " + uniq(602))]
    sumo = {g["id"]: g["cands"] for g in sections(items)["sport"]["groups"]}["sumo"]
    assert len(sumo) == 1 and "preview" not in sumo[0].item["title"]


def test_sumo_during_basho_cap_two_and_event_boost():
    events = [{"name": "Kyushu basho", "discipline": "sumo", "start": "2026-11-08", "end": "2026-11-22"}]
    day = date(2026, 11, 10)
    now = datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc)
    items = []
    for i in range(4):
        x = it("sumo", "Day 2 result " + uniq(700 + i))
        x["published"] = x["first_seen"] = (now - timedelta(hours=2 + i)).isoformat()
        items.append(x)
    assert active_disciplines(events, day) == {"sumo"}
    sport = sections(items, now=now, day=day, events=events)["sport"]
    sumo = {g["id"]: g["cands"] for g in sport["groups"]}["sumo"]
    assert len(sumo) >= 2


def test_chess_cap_boost_penalty_and_source_max():
    items = [it("chessA", uniq(800 + i)) for i in range(6)] + [it("chessB", uniq(810 + i)) for i in range(6)]
    items += [it("chessB", "Candidates 2026 round 3 report " + uniq(820), 10), it("chessA", "Daily puzzle " + uniq(821), 0.1)]
    chosen = flat(sections(items)["chess"])
    assert len(chosen) <= 6   # 2 sources x max 3
    titles = [c.item["title"] for c in chosen]
    assert any("Candidates" in t for t in titles)
    assert not any("puzzle" in t for t in titles)


def test_every_section_within_cap_on_a_big_pool():
    items = [it(s["id"], uniq(1000 + 50 * k + i), i * 1.5) for k, s in enumerate(CFG["sources"]) for i in range(12)]
    for sid, sec in sections(items).items():
        chosen = flat(sec)
        assert len(chosen) <= sec["cap"], sid
        assert max(Counter(c.source for c in chosen).values()) <= 3, sid


def test_deterministic():
    items = [it(s["id"], uniq(2000 + 50 * k + i), i) for k, s in enumerate(CFG["sources"]) for i in range(5)]
    a = [c.item["id"] for s in sections(items).values() for c in flat(s)]
    b = [c.item["id"] for s in sections(list(reversed(items))).values() for c in flat(s)]
    assert a == b


def test_event_window_includes_morning_after():
    ev = [{"name": "Paris-Roubaix", "discipline": "cycling", "start": "2027-04-11"},
          {"name": "Minor race", "discipline": "cycling", "start": "2027-05-01", "boost": False}]
    assert active_disciplines(ev, date(2027, 4, 11)) == {"cycling"}
    assert active_disciplines(ev, date(2027, 4, 12)) == {"cycling"}
    assert active_disciplines(ev, date(2027, 4, 13)) == set()
    assert active_disciplines(ev, date(2027, 5, 1)) == set()
