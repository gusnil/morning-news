# Build brief: personal morning news site

Owner: Gustav (GitHub `gusnil`). Written 22.10.2026. This document is self-contained; the build agent needs nothing else.

## 1. Outcome

A static website, rebuilt every night at 03:00 Europe/Zurich, that gives Gustav a five-minute scan of five sections — World, Basel, Sport, Chess, AI — drawn from a fixed list of credible RSS/Atom feeds. No LLM, no runtime backend, no database, no translation (the reader's browser translates). Hosted free from a GitHub repo in Gustav's account; usable as a browser home page.

Definition of done: the site has rebuilt unattended for 7 consecutive nights, every section is populated each morning, and a feed outage never produces an empty page or a failed deploy.

## 2. Hard constraints

| Constraint | Meaning for the build |
|---|---|
| No AI in the loop | No LLM, embedding, or ML call anywhere in ingest, ranking, or render. Deterministic code only. |
| No translation | Items are shown in their source language with a correct `lang` attribute on each item so Brave/Chrome auto-translate works. |
| Scan density | 8–10 items per section (sub-sections share the cap as specified in §5). Headline + source + time + optional one-line excerpt. |
| Rolling archive | 7 days. Older builds deleted at build time. |
| No live data | Article feeds only. No scores, standings, or fixture APIs. |
| Credible sources only | Only the feeds listed in §5 and their listed fallbacks. Do not add aggregators (Google News, Yahoo, MSN), content farms, or social media. Do not scrape sites that publish no feed. |
| Public | Public repo, public site, unlisted URL. No auth. |
| Zero cost | GitHub Actions free tier + GitHub Pages. No paid services. |

## 3. Architecture

```
feeds.yaml ──► fetch.py ──► normalise ──► dedupe/cluster ──► rank ──► render.py ──► site/
                 │                                                        │
            cache/*.json (7-day item cache, committed)              GitHub Pages
```

| Layer | Decision |
|---|---|
| Language | Python 3.12, stdlib + `feedparser`, `jinja2`, `pyyaml`, `python-dateutil`. Nothing else. |
| Config | `feeds.yaml` is the single source of truth for sources, sections, weights, keyword rules. Changing the site = editing YAML. |
| Cache | `cache/items.json`: every item seen in the last 7 days (id, url, title, excerpt, source, section, published, first_seen, lang). Committed on each build so the archive survives runner resets. |
| Clustering | Near-duplicate detection on normalised titles (lowercase, strip punctuation/stopwords, token set). Two items cluster if Jaccard ≥ 0.5 or one title's token set is ⊇ 70% of the other's. Clusters are scored and shown once, with the highest-weight source as the canonical link and the other sources listed as "also: X, Y". |
| Ranking | See §6. |
| Render | Jinja2 → static HTML. One `index.html` (today) + `archive/YYYY-MM-DD.html` for the previous 6 days + `archive/index.html`. One `style.css`, one `app.js` (< 3 kB). |
| Schedule | GitHub Actions cron `0 1 * * *` and `0 2 * * *` (UTC). The job exits early unless the current Europe/Zurich hour is 03. That gives exactly one 03:00 CET/CEST run year-round. Plus `workflow_dispatch` for manual runs. |
| Deploy | `actions/deploy-pages` from the `site/` folder. Build commits `cache/` back to `main` with `[skip ci]`. |
| Failure handling | A feed that fails (timeout 15 s, HTTP error, parse error) is skipped and logged; the section is filled from the cache. A build with zero successful feeds overall fails loudly (email via Actions default) and does not deploy. A section with < 4 items shows what it has plus a one-line "thin day" note — never an error. |

## 4. Repository layout

```
morning-news/
  README.md               how to run locally, how to add a feed
  feeds.yaml              all sources + rules (§5, §6)
  calendar.yaml           hand-maintained event calendar (§5, Sport)
  build/
    fetch.py              fetch + normalise + cache
    cluster.py            dedupe
    rank.py               scoring + quotas
    render.py             jinja → site/
    build.py              entrypoint: fetch → cluster → rank → render
    validate_feeds.py     checks every feed in feeds.yaml, prints status table
  templates/
    base.html, index.html, section.html, archive.html
  static/
    style.css, app.js
  cache/items.json
  site/                   build output (gitignored except in Pages artifact)
  .github/workflows/build.yml
  tests/                  pytest: cluster, rank, quotas, DST guard
```

## 5. Sections and sources

Feed URLs below are candidates from memory. **First build task is `validate_feeds.py`**: hit every URL, confirm it returns a parseable feed with items dated within 30 days, correct the URL where the site has moved it (look for `<link rel="alternate" type="application/rss+xml">` on the homepage), and record the verified URL in `feeds.yaml`. Drop a source only if no feed exists at all; note it in the README.

Columns: weight (1–5, used in ranking), lang (BCP-47), notes.

### 5.1 World (cap 10)

Design intent: balance by source origin, not by topic. Wire-agency and public-broadcaster feeds carry weight 4–5; opinion-heavy outlets weight 2–3. Regional quota in §6.

| Source | Candidate feed | Weight | Region | Lang |
|---|---|---|---|---|
| France 24 (AFP wire) | https://www.france24.com/en/rss | 5 | EU | en |
| Al Jazeera English | https://www.aljazeera.com/xml/rss/all.xml | 4 | ME | en |
| DW English | https://rss.dw.com/rdf/rss-en-all | 4 | EU | en |
| BBC World | https://feeds.bbci.co.uk/news/world/rss.xml | 3 | EU | en |
| NHK World | https://www3.nhk.or.jp/nhkworld/en/news/ (find feed) | 4 | ASIA | en |
| The Hindu – International | https://www.thehindu.com/news/international/feeder/default.rss | 4 | ASIA | en |
| South China Morning Post – World/China | https://www.scmp.com/rss/91/feed | 3 | ASIA | en |
| Africanews | https://www.africanews.com/feed/rss | 4 | AFR | en |
| El País English | https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada | 3 | EU/LATAM | en |
| Folha de S.Paulo International | https://www1.folha.uol.com.br/internacional/en/rss091.xml | 3 | LATAM | en |
| swissinfo (SWI) | https://www.swissinfo.ch/eng/rss | 3 | EU | en |
| AP News | No official RSS. Test `https://rsshub.app/apnews/topics/apf-topnews`; if unstable, drop. | 5 | US | en |

Reuters publishes no public feed; its reporting reaches the page indirectly via other outlets. Do not scrape reuters.com.

### 5.2 Basel / Switzerland (cap 10: ≥ 6 Basel-region, remainder national)

| Source | Candidate feed | Weight | Scope | Lang |
|---|---|---|---|---|
| bz Basel | https://www.bzbasel.ch/ (find feed; CH Media publishes per-section RSS) | 5 | Basel | de |
| Basler Zeitung | https://www.bazonline.ch/ (Tamedia RSS; paywalled — headlines still useful) | 4 | Basel | de |
| SRF Regionaljournal Basel Baselland | https://www.srf.ch/news/bnf/rss/1890 | 5 | Basel | de |
| Prime News | https://primenews.ch/feed | 4 | Basel | de |
| OnlineReports | https://www.onlinereports.ch/ (find feed) | 3 | Basel | de |
| Baseljetzt | https://www.baseljetzt.ch/ (find feed) | 3 | Basel | de |
| Telebasel | https://telebasel.ch/feed | 3 | Basel | de |
| Kanton Basel-Landschaft – Medienmitteilungen | https://www.baselland.ch/ (find feed) | 3 | BL | de |
| Gemeinde Münchenstein | https://www.muenchenstein.ch/ (find feed; drop if none) | 3 | Local | de |
| SRF News (national) | https://www.srf.ch/news/bnf/rss/1646 | 4 | CH | de |
| NZZ | https://www.nzz.ch/recent.rss | 3 | CH | de |
| swissinfo (SWI) | reuse 5.1 feed, filtered to Switzerland topics | 3 | CH | en |

### 5.3 Sport (cap 12 total, split as below)

**Cycling (cap 4).** Road (UCI WorldTour, Grand Tours, Monuments, Worlds, Olympics) and XCO MTB (World Cup, Worlds, Olympics).

| Source | Candidate feed | Weight | Lang |
|---|---|---|---|
| Cyclingnews | https://www.cyclingnews.com/feeds/all/ | 5 | en |
| Velo (Outside) | https://velo.outsideonline.com/feed/ | 4 | en |
| Cycling Weekly | https://www.cyclingweekly.com/feed | 3 | en |
| Escape Collective | https://escapecollective.com/feed/ | 4 | en |
| UCI | https://www.uci.org/ (find feed) | 4 | en |
| Pinkbike | https://www.pinkbike.com/pinkbike_xml_feed.php | 3 | en |
| MTB-News.de | https://www.mtb-news.de/news/feed/ | 3 | de |

Keyword filter for MTB feeds: keep only items matching `XCO|cross-country|World Cup|Worlds|World Championship|Olympic`; Pinkbike and MTB-News are otherwise dominated by gear and gravity content.

**Teams (cap 6, max 1 item per team per day, most recent first).** Teams: New England Patriots, Boston Celtics, UConn men's basketball, Boston Red Sox, FC Basel, Malmö FF, Sweden men's national football team. In the off-season a team may have no item; the slot is released to other teams, then to College Football.

| Team | Source | Candidate feed | Lang |
|---|---|---|---|
| Patriots | Official | https://www.patriots.com/rss/article | en |
| Patriots | ESPN NFL (filter: Patriots) | https://www.espn.com/espn/rss/nfl/news | en |
| Celtics | Official | https://www.nba.com/celtics/ (find feed) | en |
| Celtics | ESPN NBA (filter: Celtics) | https://www.espn.com/espn/rss/nba/news | en |
| Red Sox | Official | https://www.mlb.com/redsox/feeds/news/rss.xml | en |
| UConn MBB | Official | https://uconnhuskies.com/rss?path=mbball | en |
| FC Basel | Official | https://www.fcb.ch/ (find feed) | de |
| FC Basel | bz Basel Sport (filter: FCB) | from 5.2 | de |
| Malmö FF | Official | https://www.mff.se/ (find feed) | sv |
| Malmö FF | Sydsvenskan Sport (filter: MFF, Malmö FF) | https://www.sydsvenskan.se/ (find feed) | sv |
| Sweden NT | Fotbollskanalen (filter: landslaget, Sverige) | https://www.fotbollskanalen.se/rss/ | sv |
| Sweden NT | SvFF | https://www.svenskfotboll.se/ (find feed) | sv |

**College Football Top 25 (cap 1, weekdays; cap 2 on Sunday/Monday).** ESPN CFB feed https://www.espn.com/espn/rss/ncf/news, filter: `Top 25|No\. [1-9]|No\. 10|ranked|AP poll|CFP`. Only top-10 relevance: keep items mentioning "No. 1" to "No. 10" or "playoff".

**Sumo (cap 1; cap 2 during a basho).** Grand Sumo makuuchi only. Bashos run 15 days from the second Sunday of January, March, May, July, September, November — encode in `calendar.yaml`. Sources: Tachiai https://tachiai.org/feed/ (en, weight 4), Japan Times Sumo https://www.japantimes.co.jp/sports/sumo/feed/ (en, 4), NHK World Grand Sumo https://www3.nhk.or.jp/nhkworld/en/tv/sumo/ (find feed, 4), Japan Sumo Association https://www.sumo.or.jp/En/ (find feed; drop if none). Outside a basho, show at most one item and only if it matches `banzuke|promotion|retire|yokozuna|ozeki`.

**`calendar.yaml`.** Hand-maintained list of dated events (Grand Tours, Monuments, Road Worlds, XCO World Cup rounds, XCO Worlds, Olympics, bashos, CFP, NFL playoffs). During an event window, items from that discipline get +2 score and the sub-section cap rises by 2. The agent populates it for 2026–2027 from UCI and JSA published calendars; Gustav updates it once a year.

### 5.4 Chess (cap 8)

| Source | Candidate feed | Weight | Lang |
|---|---|---|---|
| Chess.com News | https://www.chess.com/rss/news | 4 | en |
| Lichess blog | https://lichess.org/blog.atom | 3 | en |
| ChessBase | https://en.chessbase.com/feed | 5 | en |
| FIDE | https://www.fide.com/news (find feed) | 5 | en |
| The Week in Chess | https://theweekinchess.com/ (find feed) | 4 | en |
| Chessdom | https://www.chessdom.com/feed/ | 3 | en |

Boost keywords (+1): `Candidates|World Championship|Tata Steel|Norway Chess|Sinquefield|Grand Chess Tour|Freestyle|Champions Chess Tour|Titled Tuesday|Olympiad|Grand Swiss|World Cup|Rapid & Blitz|Bundesliga`. Penalise (−2): `puzzle|lesson|course|how to|opening guide|tips`.

### 5.5 AI / decision support (cap 8)

Intent: Databricks platform news, and practical AI-augmented decision support and BI. Not model-release churn.

| Source | Candidate feed | Weight | Lang |
|---|---|---|---|
| Databricks blog | https://www.databricks.com/feed | 5 | en |
| Databricks engineering / product (if separate feed) | find on site | 5 | en |
| The Batch (deeplearning.ai) | https://www.deeplearning.ai/the-batch/feed/ | 4 | en |
| Import AI (Jack Clark) | https://importai.substack.com/feed | 4 | en |
| MIT Technology Review – AI | https://www.technologyreview.com/topic/artificial-intelligence/feed | 3 | en |
| Benedict Evans | https://www.ben-evans.com/benedictevans?format=rss | 3 | en |
| Simon Willison | https://simonwillison.net/atom/everything/ | 3 | en |
| McKinsey Insights – AI / Analytics | find feed | 3 | en |
| Gartner Newsroom | https://www.gartner.com/en/newsroom (find feed) | 3 | en |
| Microsoft Power BI blog | https://powerbi.microsoft.com/en-us/blog/feed/ | 2 | en |
| Tableau blog | find feed | 2 | en |
| Snowflake blog (competitor context) | find feed | 2 | en |

Boost (+2): `decision|decision support|decision intelligence|BI|business intelligence|analytics|dashboard|Genie|lakehouse|Unity Catalog|Mosaic|agent|forecasting|semantic layer|pharma|life sciences|R&D|clinical`. Penalise (−2): `funding|raises|valuation|benchmark|leaderboard|parameters|GPU`.

## 6. Ranking

Per item, computed at build time:

```
score = source_weight
      + 1.5 * ln(1 + n_sources_in_cluster)
      + keyword_boosts − keyword_penalties
      + recency, where recency = 3 * 0.5^(age_hours / 18)
```

Then per section: sort by score, apply caps from §5, and apply quotas:

- World: no single region > 35% of slots; at least one item each from ASIA, AFR, LATAM, ME when any exists in the candidate pool; items carried by only one source rank below any multi-source cluster regardless of score.
- Basel: ≥ 6 Basel-region slots before national fills.
- Sport: sub-section caps as in §5.3, released to other sub-sections when unfilled.
- Everything: max 3 items per source per section per day.

Deterministic tie-break: newer first, then source name.

## 7. Page design

Minimal, text-first, fast. No framework, no web fonts, no analytics, no cookies, no images.

| Element | Spec |
|---|---|
| Layout | Single page, max-width 720 px, 16 px gutters, system font stack (`-apple-system, Segoe UI, Roboto, sans-serif`), 16–17 px body, 1.55 line-height. |
| Nav | Sticky top bar with five section links (World · Basel · Sport · Chess · AI) and a date. Active section highlighted on scroll. Keys 1–5 jump to sections; `j`/`k` move between items; `Enter` opens the focused item in a new tab. |
| Item | Headline (link, `target=_blank`, `rel=noopener`), then a muted line: source · HH:MM · "also: X, Y" when clustered. Excerpt only if ≤ 160 chars and not a repeat of the headline. `lang` attribute set per item; sub-section headings in English. |
| Sport | Sub-section labels inline (Cycling / Teams / College football / Sumo) as small caps, not separate nav entries. |
| Theme | Light/dark via `prefers-color-scheme`. Two colour tokens beyond neutrals: one accent for links/active nav, one muted for metadata. |
| Footer | "Built 03:02 · 47 of 49 feeds OK · archive". Archive link lists the last 7 days. |
| Performance | Whole page < 60 kB. Lighthouse ≥ 98 on performance/accessibility. No layout shift. |
| Home page use | Page must render the full content without JavaScript; JS only adds keyboard nav and active-section highlight. |

Archive pages are the same template with the date in the nav and a "today" link.

## 8. GitHub setup

1. Gustav creates an empty **public** repository `gusnil/morning-news` (GitHub Pages on the free plan requires a public repo). The agent then attaches it and pushes.
2. Repo settings → Pages → Source: GitHub Actions.
3. Workflow permissions: `contents: write` (for cache commit), `pages: write`, `id-token: write`.
4. Site URL will be `https://gusnil.github.io/morning-news/`. Put it in the README.

Workflow skeleton:

```yaml
name: build
on:
  schedule:
    - cron: "0 1 * * *"
    - cron: "0 2 * * *"
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - id: guard
        run: python build/dst_guard.py   # exits 0 + sets run=true only when Europe/Zurich hour == 3, or on workflow_dispatch
      - if: steps.guard.outputs.run == 'true'
        run: python build/build.py
      - if: steps.guard.outputs.run == 'true'
        run: |
          git config user.name "morning-news-bot"
          git config user.email "bot@users.noreply.github.com"
          git add cache/items.json && git commit -m "cache $(date -u +%F) [skip ci]" || true
          git push
      - if: steps.guard.outputs.run == 'true'
        uses: actions/upload-pages-artifact@v3
        with: { path: site }
  deploy:
    needs: build
    if: needs.build.outputs.run == 'true'
    permissions: { pages: write, id-token: write }
    environment: { name: github-pages }
    runs-on: ubuntu-latest
    steps:
      - uses: actions/deploy-pages@v4
```

## 9. Build sequence for the agent

1. Scaffold repo layout (§4), `requirements.txt`, README.
2. Write `validate_feeds.py`; run it against every candidate in §5; fix URLs; commit verified `feeds.yaml`. Report the table of dead/missing feeds to Gustav in the first progress message.
3. Implement fetch + cache, then cluster, then rank with unit tests (clustering on synthetic near-duplicates; quota enforcement; DST guard for four dates: mid-January, mid-July, last Sunday of March, last Sunday of October).
4. Implement templates and CSS; build locally; open `site/index.html` and check against §7.
5. Populate `calendar.yaml` for the next 12 months from UCI (road + MTB) and JSA calendars.
6. Push; enable Pages; run `workflow_dispatch`; confirm the site is live.
7. Hand over with: site URL, the feed status table, and a one-paragraph note on how to add or remove a source.

## 10. Acceptance checks

| Check | Pass condition |
|---|---|
| Nightly run | Workflow runs once per night at 03:00 local, both in October (CEST) and after 25.10.2026 (CET). No duplicate run. |
| Resilience | Kill 20% of feeds (point them at 404) and rebuild: deploy still succeeds, affected sections fill from cache, footer shows the feed count. |
| Caps and quotas | Every section ≤ its cap; World has no region > 35%; no source > 3 items per section. |
| Clustering | Same story from three outlets appears once with "also:" line. |
| Density | Full page readable in under five minutes; no section longer than one screen at 1080p. |
| Translation hook | Each German/Swedish item carries `lang="de"`/`lang="sv"`; Brave's translate prompt triggers on the page. |
| No AI | `grep -ri "openai\|anthropic\|deepl\|translate\|embedding"` in `build/` returns nothing. |
| Archive | Exactly 7 dated pages exist after 8 nights. |
| Home page | Page loads fully with JS disabled; < 60 kB; Lighthouse ≥ 98. |

## 11. Out of scope (deliberately)

LLM summaries or digests; live scores and standings; any translation; auth; a mobile app; newsletters or push; comments; search. Each could be added later as a separate module without touching the nightly pipeline.
