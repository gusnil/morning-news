import re, urllib.request, gzip, json, feedparser
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"
def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}), timeout=25)
    b = r.read(); return gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" else b
out = {}
for page in ["https://www.srf.ch/really-simple-syndication-rss-feeds-von-srf", "https://www.srf.ch/news/regional/basel-baselland", "https://www.srf.ch/news/schweiz/basel-baselland", "https://www.srf.ch/audio/regionaljournal-basel-baselland"]:
    try:
        t = get(page).decode("utf-8", "replace")
        out[page] = {"rss": sorted(set(re.findall(r"[a-z/:.]*srf\.ch[^\"'\s<>]*rss[^\"'\s<>]*|/news/bnf/rss/\d+|rss/\d+", t)))[:200],
                     "basel": [re.sub(r"\s+", " ", t[max(0,m.start()-200):m.end()+200]) for m in re.finditer(r"Basel", t)][:10]}
    except Exception as e:
        out[page] = str(e)
titles = {}
for n in list(range(1640, 1700)) + list(range(1880, 1960)):
    u = f"https://www.srf.ch/news/bnf/rss/{n}"
    try:
        fp = feedparser.parse(get(u))
        if fp.entries: titles[n] = [fp.feed.get("title"), len(fp.entries), fp.entries[0].get("title")]
    except Exception:
        pass
out["ids"] = titles
json.dump(out, open("probe/srf.json", "w"), indent=1, ensure_ascii=False)
