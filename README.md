# morning-news

A personal, static news page: weather, World, Basel, Sport, Chess, AI, R&D. Rebuilt three times a day (01:13, 11:43, 17:43 Europe/Zurich) by GitHub Actions from a fixed list of RSS/Atom feeds, and served by GitHub Pages. There's no LLM, no translation, no backend and no tracking. The specification is in [`BRIEF.md`](BRIEF.md).

**Site:** https://gusnil.github.io/morning-news/ (live once Pages is enabled; see *Setup* below).

## How it works

```
feeds.yaml -> build/fetch.py -> cache/items.json -> build/cluster.py -> build/rank.py -> build/render.py -> site/
```

| Step | What happens |
|---|---|
| Fetch | Every active feed is fetched once (15 s timeout). A failing feed is logged and skipped. If **all** feeds fail, the build exits non-zero and nothing is deployed. |
| Cache | `cache/items.json` holds every item from the last 7 days. `cache/pages.json` holds the rendered selection for each of the last 7 days. The workflow commits both back to `main`, so the archive survives runner resets and a dead feed's section is filled from the cache. |
| Cluster | Near-duplicate headlines (Jaccard >= 0.5 on normalised token sets, or >= 70% containment) are shown once, with the highest-weight source as the link and "also: X, Y". |
| Rank | `weight + 1.5*ln(1+sources) + keyword boosts - penalties + 3*0.5^(age/18h)`, +2 during `calendar.yaml` events. Caps and quotas follow BRIEF §5/§6. |
| Render | `site/index.html` (today), `site/archive/YYYY-MM-DD.html` (last 7 days, today included) and `site/archive/index.html`. One CSS and one JS file. The page is about 20 kB and works fully without JavaScript. |
| Schedule | Six UTC crons (two per edition, one for CEST and one for CET) at off-peak minutes. `build/dst_guard.py` lets through only runs whose **scheduled** slot is 01:xx, 11:xx or 17:xx in Zurich, so there are exactly three builds a day in both CET and CEST, even when GitHub starts a job hours late. Manual runs and pushes to templates/static/build/feeds.yaml always build. |

Keys on the page: `1`–`5` jump to a section, `j`/`k` move between items, `Enter` opens the focused item in a new tab.

## Run locally

```sh
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
python build/build.py              # fetch feeds, update cache/, write site/
python build/build.py --no-fetch   # re-render site/ from cache/ only
python -m pytest -q                # tests
python build/validate_feeds.py     # check every feed in feeds.yaml
```

Then open `site/index.html` in a browser.

## Add, change or remove a source

Edit `feeds.yaml`. To add a source, copy an existing entry in the same section and set `id`, `name`, `url`, `weight` (1–5) and `lang`. World sources also need `region` (EU, ME, ASIA, AFR, LATAM, US). Basel sources need `scope` (Basel, BL, Local or CH). Sport sources need `sub`, and team sources need `team`. Add `include`/`exclude` regexes if the feed needs filtering. Push the change. The **validate-feeds** workflow runs automatically, re-checks every feed from GitHub's network and commits the result to [`feeds-status.md`](feeds-status.md). To remove a source, delete its entry, or set `status: dropped` so the history stays visible. Sources with `status: blocked` are skipped by the nightly build but still re-checked by the weekly validation, so if one becomes reachable again, set it back to `verified`.

## Sources (validated 22.10.2026 from GitHub Actions)

Validation criteria: the feed parses, has at least 1 item, and its newest item is no more than 30 days old. The sandbox used to build this project could not reach any news site, so every check ran inside GitHub Actions, which is the same network the nightly build uses.

67 entries: 40 verified, 3 stale (working feed, posts rarely), 8 blocked (the site refuses GitHub's runners, so the feed can't be fetched where the build runs), 16 dropped (no feed exists). No source is marked *unverified*: every check was run from GitHub Actions.

| Section | Source | Status | Feed URL / reason |
|---|---|---|---|
| world | France 24 (`france24`) | verified | https://www.france24.com/en/rss |
| world | Al Jazeera (`aljazeera`) | verified | https://www.aljazeera.com/xml/rss/all.xml |
| world | DW (`dw`) | verified | https://rss.dw.com/rdf/rss-en-all |
| world | BBC World (`bbc`) | verified | https://feeds.bbci.co.uk/news/world/rss.xml |
| world | NHK World (`nhk`) | dropped | No news feed since NHK World relaunch (old URLs 404; only a stale features feed /nhkworld/data/en/news/backstory/rss.xml remains). |
| world | The Hindu (`thehindu`) | verified | https://www.thehindu.com/news/international/feeder/default.rss |
| world | SCMP (`scmp`) | verified | https://www.scmp.com/rss/91/feed |
| world | Africanews (`africanews`) | verified | https://www.africanews.com/feed/rss |
| world | El País English (`elpais`) | verified | https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada |
| world | Folha (`folha`) | verified | https://www1.folha.uol.com.br/internacional/en/rss091.xml |
| world | swissinfo (`swissinfo`) | dropped | All swissinfo.ch WordPress feeds return 410 No feed available (checked /eng/rss, /eng/feed, ?feed=rss2, category feeds). |
| world | AP News (`apnews`) | dropped | rsshub.app returns 403 to feed readers and says it is for testing only; no official AP feed. |
| basel | bz Basel (`bzbasel`) | blocked | Cloudflare challenge (403) for GitHub Actions runners on every URL incl. homepage; feed URL could not be verified. |
| basel | Basler Zeitung (`baz`) | verified | https://partner-feeds.publishing.tamedia.ch/rss/bazonline/basel (Paywalled; headlines still useful.) |
| basel | SRF Regionaljournal (`srf_basel`) | dropped | SRF publishes no Basel regional feed (checked its RSS directory, 2026-10-22). /rss/1890 is the national 'Schweiz - Inland' feed and is used by srf_news. |
| basel | Prime News (`primenews`) | dropped | No feed: homepage advertises none; /feed, /rss, /rss.xml, /api/rss-feed all 404. |
| basel | OnlineReports (`onlinereports`) | verified | https://onlinereports.ch/api/rss-feed |
| basel | 20 Minuten Basel (`20min_basel`) | verified | https://partner-feeds.20min.ch/rss/20minuten/regionen/basel |
| basel | Bajour (`bajour`) | verified | https://bajour.ch/api/rss-feed |
| basel | Kanton Basel-Stadt (`bs_medien`) | verified | https://www.bs.ch/rss (undated items) |
| basel | Blick Basel (`blick_basel`) | stale | https://www.blick.ch/schweiz/basel/rss.xml |
| basel | Nau.ch Basel, barfi.ch, Wochenblatt Birseck, Riehener Zeitung, SRF Regionaljournal podcast | dropped | no usable feed |
| basel | Baseljetzt (`baseljetzt`) | dropped | baseljetzt.ch now redirects to telebasel.ch, which publishes no feed. |
| basel | Telebasel (`telebasel`) | dropped | No feed: homepage advertises none; /feed, /rss, /rss.xml, /api/rss all 404. |
| basel | Kanton BL (`baselland`) | blocked | Cloudflare challenge (403) for GitHub Actions runners; feed could not be discovered or verified. |
| basel | Gemeinde Münchenstein (`muenchenstein`) | dropped | No feed: i-web CMS page embeds news as JSON, no RSS link; common paths 404. |
| basel | SRF News (`srf_news`) | verified | https://www.srf.ch/news/bnf/rss/1890 (Uses SRF 'Schweiz - Inland' (1890); the brief's 1646 mixes in international news.) |
| basel | NZZ (`nzz`) | verified | https://www.nzz.ch/recent.rss |
| basel | swissinfo (`swissinfo_ch`) | dropped | Same swissinfo feed, gone (410). |
| sport/cycling | Cyclingnews (`cyclingnews`) | verified | https://www.cyclingnews.com/feeds/all/ |
| sport/cycling | Velo (`velo`) | verified | https://velo.outsideonline.com/feed/ |
| sport/cycling | Cycling Weekly (`cyclingweekly`) | verified | https://www.cyclingweekly.com/feeds.xml |
| sport/cycling | Escape Collective (`escape`) | verified | https://escapecollective.com/feed/ |
| sport/cycling | UCI (`uci`) | dropped | No feed: uci.org advertises none; /rss, /feed, /news/rss all 404. |
| sport/cycling | Pinkbike (`pinkbike`) | verified | https://www.pinkbike.com/pinkbike_xml_feed.php |
| sport/cycling | MTB-News.de (`mtbnews`) | verified | https://www.mtb-news.de/news/feed/ |
| sport/teams | Patriots.com (`patriots`) | verified | https://www.patriots.com/rss/news |
| sport/teams | ESPN (`espn_nfl`) | blocked | ESPN answers GitHub runners with an AWS WAF challenge (HTTP 202 HTML), not the feed. |
| sport/teams | Celtics.com (`celtics`) | dropped | nba.com/celtics publishes no feed (page has no feed link; rss.xml 403 Akamai). |
| sport/teams | ESPN (`espn_nba`) | blocked | ESPN AWS WAF challenge for GitHub runners. |
| sport/teams | MLB.com (`redsox`) | verified | https://www.mlb.com/redsox/feeds/news/rss.xml |
| sport/teams | UConn Huskies (`uconn`) | verified | https://uconnhuskies.com/rss?path=mbball |
| sport/teams | FC Basel (`fcb`) | dropped | No feed: fcb.ch advertises none; common paths 404 or HTML. |
| sport/teams | bz Basel (`bz_fcb`) | blocked | bzbasel.ch Cloudflare challenge for GitHub runners. |
| sport/teams | SRF Sport (`srf_fcb`) | verified | https://www.srf.ch/news/bnf/rss/2562 (Fallback for FC Basel (official site and bz Basel unavailable): SRF Fussball feed filtered to FCB.) |
| sport/teams | Malmö FF (`mff`) | verified | https://www.mff.se/nyheter/feed/ |
| sport/teams | Sydsvenskan (`sydsvenskan`) | verified | https://www.sydsvenskan.se/feeds/section/sport/feed.xml |
| sport/teams | Fotbollskanalen (`fotbollskanalen`) | dropped | No feed: /rss/ and common paths 404; homepage advertises none. |
| sport/teams | SvFF (`svff`) | verified | https://www.svenskfotboll.se/rss.xml (Items carry no dates; first-seen time is used.) |
| sport/cfb | ESPN (`espn_cfb`) | blocked | ESPN AWS WAF challenge for GitHub runners; college football has no other listed source. |
| sport/sumo | Tachiai (`tachiai`) | verified | https://tachiai.org/feed/ |
| sport/sumo | Japan Times (`japantimes_sumo`) | verified | https://www.japantimes.co.jp/sports/feed/ (/sports/sumo/feed/ redirects to the homepage; uses the Japan Times sports feed filtered to sumo.) |
| sport/sumo | NHK World Sumo (`nhk_sumo`) | dropped | No feed on the NHK World sumo page. |
| sport/sumo | Japan Sumo Association (`jsa`) | dropped | No feed on sumo.or.jp/En/. |
| chess | Chess.com (`chesscom`) | verified | https://www.chess.com/rss/news |
| chess | Lichess (`lichess`) | verified | https://lichess.org/blog.atom |
| chess | ChessBase (`chessbase`) | verified | https://en.chessbase.com/feed |
| chess | FIDE (`fide`) | verified | https://www.fide.com/feed/ |
| chess | The Week in Chess (`twic`) | verified | https://theweekinchess.com/twic-rss-feed |
| chess | Chessdom (`chessdom`) | stale | https://www.chessdom.com/feed/ (Feed works but newest item was 2026-08-31 at validation; kept, costs nothing.) |
| ai | Databricks (`databricks`) | verified | https://www.databricks.com/feed |
| ai | Databricks Engineering (`databricks_eng`) | dropped | No separate engineering/product feed; the category page links to the main /feed. |
| ai | The Batch (`thebatch`) | blocked | deeplearning.ai returns 403 (Cloudflare) to GitHub runners. |
| ai | Import AI (`importai`) | verified | https://jack-clark.net/feed/ (importai.substack.com returns 403 to GitHub runners; jack-clark.net carries the same issues.) |
| ai | MIT Technology Review (`mittr`) | verified | https://www.technologyreview.com/topic/artificial-intelligence/feed |
| ai | Benedict Evans (`benevans`) | stale | https://www.ben-evans.com/benedictevans?format=rss (Low-frequency essays; newest item 2026-09-03 at validation.) |
| ai | Simon Willison (`willison`) | verified | https://simonwillison.net/atom/everything/ |
| ai | McKinsey (`mckinsey`) | verified | https://www.mckinsey.com/insights/rss |
| ai | Gartner (`gartner`) | blocked | gartner.com returns 403 to GitHub runners. |
| ai | Power BI blog (`powerbi`) | verified | https://powerbi.microsoft.com/en-us/blog/feed/ |
| ai | Tableau blog (`tableau`) | stale | https://www.tableau.com/feed.rss (Feed works; newest item 2026-07-20 at validation.) |
| ai | Snowflake blog (`snowflake`) | verified | https://www.snowflake.com/feed/ |

**Coverage gaps that follow from this:** college football has no working source, because ESPN is its only listed feed. The Celtics have no source (no official feed, and ESPN is blocked). FC Basel depends on the SRF Basel feed filtered for FCB. When a team has no item, its slot goes to other teams and then to other sub-sections, as the brief specifies.

## Calendar

`calendar.yaml` lists sumo bashos, CFP rounds, NFL playoffs, every 2027 UCI WorldTour race (Grand Tours, Monuments and Worlds boost; the rest are reference only), the 2027 Worlds in Haute-Savoie and the XCO World Cup. Entries marked `confirmed: false` (all 2027 XCO World Cup rounds, which so far exist only as a leaked draft) must be checked once the UCI publishes the official MTB calendar. Sources are listed in the file header. Update the file once a year.

## Setup (one-time, repository owner)

1. Settings -> Pages -> Build and deployment -> Source: **GitHub Actions**.
2. GitHub Pages on the free plan needs a **public** repository (the brief specifies a public repo). If the repository is private, either make it public (Settings -> General -> Danger Zone -> Change visibility) or use a paid plan.
3. Actions -> **build** -> Run workflow, for the first deploy. After that it runs nightly.
