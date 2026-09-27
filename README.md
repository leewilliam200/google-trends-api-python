# Google Trends API for Python (pytrends alternative)

A maintained way to get **Google Trends data from Python**: interest over time, interest by region, related
queries (top and rising) and a plain-English trend summary per keyword, for **one keyword or thousands**.

[pytrends](https://github.com/GeneralMills/pytrends) was archived by its owner in April 2025 and sends every
request from your own IP, so bulk jobs hit Google's `429 Too Many Requests`. This library calls the hosted
[Google Trends Scraper & API](https://apify.com/meridianlabs/google-trends-scraper) on Apify instead: proxies and
retries run on the server, so there are **no 429s to handle**, and it keeps the **pytrends interface**.

```diff
- from pytrends.request import TrendReq
+ from google_trends_api import TrendReq

- pytrends = TrendReq(hl="en-US", tz=360)
+ pytrends = TrendReq(hl="en-US", tz=360, apify_token="<YOUR_APIFY_TOKEN>")
  pytrends.build_payload(["air fryer", "standing desk"], timeframe="today 12-m", geo="US")
  df = pytrends.interest_over_time()
```

## Install

```bash
pip install "google-trends-api-python[pandas] @ git+https://github.com/leewilliam200/google-trends-api-python"
```

Get an Apify API token in [Apify Console](https://console.apify.com) → Settings → API & Integrations, then
`export APIFY_TOKEN=...` or pass `apify_token=`.

## Quick start: the pytrends way

```python
from google_trends_api import TrendReq

pytrends = TrendReq(apify_token="<YOUR_APIFY_TOKEN>")
pytrends.build_payload(["air fryer", "standing desk"], timeframe="today 12-m", geo="US")

pytrends.interest_over_time()     # date index, one column per keyword, isPartial
pytrends.interest_by_region()     # geoName index, one column per keyword
pytrends.related_queries()        # {keyword: {"top": DataFrame, "rising": DataFrame}}
pytrends.summary()                # new: momentum, year-on-year change, peak, seasonality, text
```

One `build_payload()` is **one hosted run**: `interest_over_time()`, `interest_by_region()` and
`related_queries()` all read the same result, so you pay once per keyword, not once per method.

## Bulk: hundreds of keywords in one call

```python
from google_trends_api import GoogleTrends

gt = GoogleTrends(max_cost_usd=2.00)          # token from $APIFY_TOKEN; hard cap per run
res = gt.lookup(
    ["halloween costume", "pool float", "ski jacket", "sunscreen"],
    geo="US",
    timeframe="today 5-y",                     # 5 years gives seasonality and year-on-year change
)

print(res.summary()[["momentum", "yearOnYearChangePct", "seasonal", "seasonalPeakMonth"]])
for row in res:                                # raw rows: one per keyword, with a status
    print(row["keyword"], row["status"], row["summary"]["text"])
```

Each keyword gets its own 0–100 scale unless you pass `compare=True`, which puts keywords on one scale in groups
of up to five (Google's limit).

## pytrends mapping

| pytrends | here |
|---|---|
| `TrendReq(hl, tz, timeout, retries, proxies, ...)` | same signature, plus `apify_token`; session options are ignored (retries and proxies run on the server) |
| `build_payload(kw_list, cat, timeframe, geo, gprop)` | same; up to 5 keywords, compared on one scale |
| `timeframe='today 5-y'`, `'today 12-m'`, `'today 3-m'`, `'today 1-m'`, `'now 7-d'`, `'now 1-d'`, `'now 4-H'`, `'now 1-H'`, `'all'`, `'2024-01-01 2025-06-30'` | same |
| `gprop=''`, `'images'`, `'news'`, `'youtube'`, `'froogle'` | same (`froogle` = Google Shopping) |
| `interest_over_time()` | same shape |
| `interest_by_region(resolution='COUNTRY' / 'REGION' / 'DMA')` | same; `CITY` isn't available |
| `related_queries()` | same shape; rising `value` is growth in %, and `Breakout` rows have `value=None`, `growth='Breakout'` |
| `related_topics()` | not available (see Limitations) |
| n/a | `summary()`: momentum, year-on-year change, peak, seasonality, fastest-rising related search |

## What does it cost?

The hosted Actor charges **$5 per 1,000 keyword lookups ($0.005 each)**; failed lookups are free. Apify's free
plan includes $5 of usage every month, about 1,000 lookups. Set `max_cost_usd=` and the run stops exactly there;
keywords it didn't reach come back as `skipped` and aren't charged. Full details are on the
[Actor page](https://apify.com/meridianlabs/google-trends-scraper).

## Use it from AI agents (MCP)

The same data is available to Claude, ChatGPT, Cursor and other MCP clients through Apify's MCP server:
`https://mcp.apify.com/?tools=meridianlabs/google-trends-scraper` (sign in with your Apify account). It's also
listed in the official MCP Registry as `com.meridianlabssoftware/google-trends`.

## Limitations

- **Related topics and city-level regions aren't available.** Google withholds them from automated lookups,
  including from real browsers, so no hosted service can return them reliably.
- Google Trends values are relative (0–100 within each request), exactly as in pytrends and on
  trends.google.com.

## More from Meridian Labs

- [Keyword Search Volume & CPC API + Google Trends](https://apify.com/meridianlabs/keyword-search-volume): monthly search volume, CPC and competition in bulk, with a Trends summary per keyword.
- [Greenhouse, Lever & Ashby Jobs Scraper + Salary](https://apify.com/meridianlabs/greenhouse-lever-ashby-jobs-scraper): live jobs from company boards with normalised salary.
- [Backlink Checker: Referring Domains & Spam Score](https://apify.com/meridianlabs/backlink-checker): full backlink lists, referring domains, domain rank and spam score for up to 1,000 domains per run.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest          # offline; no token or network needed
```

---

Data source: Google Trends (https://www.google.com/trends). Not affiliated with or endorsed by Google.
MIT licence.
