import urllib.request, gzip, json, feedparser
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"
def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}), timeout=25)
    b = r.read(); return gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" else b
ids = ["bnf/rss/19919909","bnf/rss/19920002","bnf/rss/19920107","bnf/rss/19920122","bnf/rss/19920818","bnf/rss/630","news/bnf/rss/19032223","sport/bnf/rss/3042","kultur/bnf/rss/10943024"]
ids += [f"news/bnf/rss/{n}" for n in (2562,2814,2958,3010,3418,454,718,787950,8726,8738,8762,8774,8786,8798)]
ids += [f"bnf/rss/{n}" for n in (2562,2814,2958,3010,3418,454,718,787950,8726,8738,8762,8774,8786,8798)]
out = {}
for i in ids:
    u = "https://www.srf.ch/" + i
    try:
        fp = feedparser.parse(get(u))
        out[u] = [fp.feed.get("title"), len(fp.entries), [e.get("title") for e in fp.entries[:4]]]
    except Exception as e:
        out[u] = str(e)[:60]
json.dump(out, open("probe/srf.json", "w"), indent=1, ensure_ascii=False)
