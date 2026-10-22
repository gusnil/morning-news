import gzip, json, re, sys, html, zlib, urllib.request, urllib.error, hashlib, os
import feedparser
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
os.makedirs("probe/text", exist_ok=True)
index = []
for line in open(sys.argv[1]):
    url = line.strip()
    if not url or url.startswith("#"): continue
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", url.split("://", 1)[1])[:90]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip", "Accept-Language": "en"})
        with urllib.request.urlopen(req, timeout=25) as r:
            b = r.read()
            if (r.headers.get("Content-Encoding") or "") == "gzip": b = gzip.decompress(b)
            st, ct = r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        index.append({"url": url, "status": e.code}); continue
    except Exception as e:
        index.append({"url": url, "status": str(e)[:80]}); continue
    fp = feedparser.parse(b)
    rec = {"url": url, "status": st, "ctype": ct[:40], "file": slug + ".txt"}
    if fp.entries:
        rec["feed_title"] = fp.feed.get("title"); rec["feed_link"] = fp.feed.get("link")
        text = "\n".join(f"{e.get('published','')} | {e.get('title','')}" for e in fp.entries)
    else:
        t = b.decode("utf-8", "replace")
        alts = re.findall(r"<link[^>]+(?:rss|atom)\+xml[^>]*>", t, re.I)
        rec["alternates"] = alts[:20]
        rec["rss_snips"] = [re.sub(r"\s+", " ", t[max(0, m.start()-120):m.end()+120]) for m in re.finditer(r"rss", t, re.I)][:15]
        if "action=raw" not in url:
            t = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", t)
            t = re.sub(r"(?i)<(br|/p|/div|/li|/tr|/h\d|/td|/th)[^>]*>", "\n", t)
            t = re.sub(r"<[^>]+>", " ", t); t = html.unescape(t)
            t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
        text = t
    open("probe/text/" + slug + ".txt", "w").write(text[:300000])
    index.append(rec)
json.dump(index, open("probe/text/index.json", "w"), indent=1)
