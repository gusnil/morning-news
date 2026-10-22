"""Near-duplicate clustering on normalised headline token sets.

Two items join a cluster when Jaccard(tokens) >= 0.5, or when one title's token
set contains >= 70% of the other's (only for titles of >= 3 tokens, so very
short headlines do not swallow everything). Clustering is single-link within a
section. The canonical item is the one from the highest-weight source.
"""
from __future__ import annotations

import re
import unicodedata

JACCARD_MIN = 0.5
CONTAIN_MIN = 0.7
MIN_TOKENS_CONTAIN = 3

STOPWORDS = set("""
a an the and or but of to in on at for from by with as is are was were be been being it its this that these
those after before over under into about against amid says said say will would can could may might new
not no than then up out off he she they we you his her their our your who what when where why how
der die das ein eine einer eines und oder aber von zu im in am an auf für mit als ist sind war waren wird
werden nach vor über unter bei aus dem den des sich nicht kein keine wie was wer wo es er sie wir
och att det som en ett är var för på med av till från den de inte har om ska efter hur vad
""".split())

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def tokens(title: str) -> frozenset[str]:
    t = unicodedata.normalize("NFKC", title).lower()
    t = t.replace("’", "'").replace("'s ", " ")
    t = _NON_WORD.sub(" ", t)
    return frozenset(w for w in t.split() if w not in STOPWORDS and (len(w) > 1 or w.isdigit()))


def similar(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    if inter / len(a | b) >= JACCARD_MIN:
        return True
    small = min(len(a), len(b))
    return small >= MIN_TOKENS_CONTAIN and inter / small >= CONTAIN_MIN


def cluster(items: list[dict], weight_of) -> list[dict]:
    """Group items into clusters. `weight_of(source_id) -> number`.

    Returns a list of {"canonical": item, "members": [items], "sources": [ids], "also": [ids]}.
    Items are first de-duplicated by URL (same link from two feeds counts as two sources).
    """
    toks = [tokens(it["title"]) for it in items]
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_url: dict[str, int] = {}
    for i, it in enumerate(items):
        j = by_url.setdefault(it["url"], i)
        if j != i:
            parent[find(i)] = find(j)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if find(i) != find(j) and similar(toks[i], toks[j]):
                parent[find(j)] = find(i)

    groups: dict[int, list[dict]] = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)

    out = []
    for members in groups.values():
        members.sort(key=lambda m: (-weight_of(m["source"]), -_ts(m), m["source"]))
        canonical = members[0]
        sources: list[str] = []
        for m in members:
            if m["source"] not in sources:
                sources.append(m["source"])
        out.append({
            "canonical": canonical,
            "members": members,
            "sources": sources,
            "also": [s for s in sources if s != canonical["source"]],
        })
    return out


def _ts(it: dict) -> float:
    from datetime import datetime
    s = it.get("published") or it.get("first_seen")
    return datetime.fromisoformat(s).timestamp() if s else 0.0
