from cluster import cluster, similar, tokens

W = {"france24": 5, "aljazeera": 4, "bbc": 3, "dw": 4}


def item(i, source, title, url=None):
    return {"id": str(i), "source": source, "title": title, "url": url or f"https://{source}.example/{i}",
            "published": "2026-10-22T05:00:00+00:00", "first_seen": "2026-10-22T05:10:00+00:00"}


def run(items):
    return cluster(items, lambda s: W.get(s, 3))


def test_same_story_three_outlets_is_one_cluster_with_also():
    items = [
        item(1, "bbc", "Earthquake of magnitude 7.1 strikes off coast of Japan"),
        item(2, "aljazeera", "Magnitude 7.1 earthquake strikes off Japan coast"),
        item(3, "france24", "Strong earthquake of magnitude 7.1 strikes off the coast of Japan, tsunami warning issued"),
        item(4, "dw", "EU leaders agree new sanctions package against Russia"),
    ]
    cls = run(items)
    assert len(cls) == 2
    quake = next(c for c in cls if len(c["members"]) == 3)
    assert quake["canonical"]["source"] == "france24"          # highest weight is canonical
    assert sorted(quake["also"]) == ["aljazeera", "bbc"]


def test_containment_rule():
    a = tokens("Swiss voters reject pension reform")
    b = tokens("Swiss voters reject pension reform in tight referendum result, turnout high")
    assert similar(a, b)


def test_unrelated_stories_stay_apart():
    cls = run([
        item(1, "bbc", "Swiss voters reject pension reform"),
        item(2, "dw", "Swiss parliament approves new defence budget"),
        item(3, "aljazeera", "Pension protests spread across France"),
    ])
    assert len(cls) == 3


def test_short_titles_do_not_overmerge():
    assert not similar(tokens("Live: Updates"), tokens("Live updates from the Gaza ceasefire talks in Cairo"))


def test_same_url_counts_once_per_cluster():
    cls = run([item(1, "bbc", "Headline A", url="https://x.org/a"), item(2, "dw", "Different words", url="https://x.org/a")])
    assert len(cls) == 1


def test_stopwords_and_punctuation_ignored():
    assert tokens("The ceasefire holds, officials say!") == tokens("Ceasefire holds: officials say")
