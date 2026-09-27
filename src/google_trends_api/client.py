"""Google Trends through the hosted Google Trends Scraper & API on Apify.

Two ways in:

* ``GoogleTrends``: bulk lookups, one row per keyword, with helpers that turn the rows into pandas DataFrames.
* ``TrendReq``: the pytrends interface (``build_payload``, ``interest_over_time`` ...), so pytrends code keeps
  working after changing one import.

Every lookup runs the Actor ``meridianlabs/google-trends-scraper`` in your Apify account and is billed per
keyword looked up (failed lookups are free). Data source: Google Trends (https://www.google.com/trends).
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Iterable, Optional

ACTOR_ID = "meridianlabs/google-trends-scraper"

# pytrends `timeframe` -> Actor `timeRange`
TIMEFRAMES = {
    "now 1-H": "past_hour",
    "now 4-H": "past_4_hours",
    "now 1-d": "past_day",
    "now 7-d": "past_7_days",
    "today 1-m": "past_30_days",
    "today 3-m": "past_90_days",
    "today 12-m": "past_12_months",
    "today 5-y": "past_5_years",
    "all": "all_time",
}
TIME_RANGES = set(TIMEFRAMES.values()) | {"custom"}

# pytrends `gprop` -> Actor `searchType`
GPROPS = {"": "web", "images": "images", "news": "news", "youtube": "youtube", "froogle": "shopping"}
SEARCH_TYPES = set(GPROPS.values())

RESOLUTIONS = {"COUNTRY", "REGION", "DMA"}   # pytrends `resolution` values we can serve (no CITY)


class TrendsError(Exception):
    """Raised for invalid arguments or a failed run."""


def _time_range(timeframe: str) -> tuple[str, Optional[str]]:
    """Accept a pytrends timeframe, an Actor time range, or 'YYYY-MM-DD YYYY-MM-DD'."""
    tf = (timeframe or "").strip()
    if tf in TIMEFRAMES:
        return TIMEFRAMES[tf], None
    if tf in TIME_RANGES and tf != "custom":
        return tf, None
    parts = tf.split()
    if len(parts) == 2 and all(len(p) == 10 and p[4] == "-" and p[7] == "-" for p in parts):
        return "custom", tf
    raise TrendsError(f"Unsupported timeframe {timeframe!r}. Use one of {sorted(TIMEFRAMES)}, "
                      f"{sorted(TIME_RANGES - {'custom'})} or 'YYYY-MM-DD YYYY-MM-DD'.")


def _search_type(value: str) -> str:
    if value in GPROPS:
        return GPROPS[value]
    if value in SEARCH_TYPES:
        return value
    raise TrendsError(f"Unsupported search type {value!r}. Use one of {sorted(GPROPS)} or {sorted(SEARCH_TYPES)}.")


def _pandas():
    try:
        import pandas as pd
    except ImportError as e:  # pragma: no cover - exercised only without pandas
        raise TrendsError("DataFrame helpers need pandas: pip install 'google-trends-api-python[pandas]'") from e
    return pd


class TrendsResult:
    """The rows of one run (one per keyword) and pandas views of them."""

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    def ok(self) -> list[dict]:
        """Rows with data (status 'ok'). Other statuses: no_data, error, skipped (the last two are not charged)."""
        return [r for r in self.rows if r.get("status") == "ok"]

    def summary(self):
        """One row per keyword: momentum, year-on-year change, peak, seasonality, top rising search, text."""
        pd = _pandas()
        recs = [{"keyword": r.get("keyword"), "status": r.get("status"), **(r.get("summary") or {})} for r in self.rows]
        return pd.DataFrame(recs).set_index("keyword") if recs else pd.DataFrame()

    def interest_over_time(self):
        """pytrends shape: a date index, one column per keyword, plus an isPartial column."""
        pd = _pandas()
        frames, partial = [], {}
        for r in self.ok():
            pts = r.get("interestOverTime") or []
            if not pts:
                continue
            s = pd.Series({p["date"]: p["value"] for p in pts}, name=r["keyword"])
            frames.append(s)
            for p in pts:
                partial[p["date"]] = partial.get(p["date"], False) or bool(p.get("isPartial"))
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, axis=1)
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df["isPartial"] = [partial.get(d.strftime("%Y-%m-%d"), False) for d in df.index]
        return df.sort_index()

    def interest_by_region(self):
        """pytrends shape: a geoName index, one column per keyword (0-100)."""
        pd = _pandas()
        frames = []
        for r in self.ok():
            regs = r.get("interestByRegion") or []
            if regs:
                frames.append(pd.Series({g["geoName"]: g["value"] for g in regs}, name=r["keyword"]))
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, axis=1)
        df.index.name = "geoName"
        return df

    def related_queries(self) -> dict[str, dict[str, Any]]:
        """pytrends shape: {keyword: {'top': DataFrame(query, value), 'rising': DataFrame(query, value)}}.

        Rising `value` is the growth in percent (e.g. 350 for +350%); Google's 'Breakout' has no number, so its
        value is None and the `growth` column says 'Breakout'. `sharesWordWithKeyword` flags Google's unrelated
        'rising' suggestions.
        """
        pd = _pandas()
        out = {}
        for r in self.ok():
            rq = r.get("relatedQueries") or {}
            top = pd.DataFrame([{"query": q["query"], "value": q.get("value"),
                                 "sharesWordWithKeyword": q.get("sharesWordWithKeyword")} for q in rq.get("top") or []])
            rising = pd.DataFrame([{"query": q["query"], "value": q.get("growthPct"), "growth": q.get("growth"),
                                    "sharesWordWithKeyword": q.get("sharesWordWithKeyword")}
                                   for q in rq.get("rising") or []])
            out[r["keyword"]] = {"top": top if len(top) else None, "rising": rising if len(rising) else None}
        return out


class GoogleTrends:
    """Bulk Google Trends lookups via the Apify Actor.

    token: your Apify API token (Console -> Settings -> API & Integrations). Defaults to $APIFY_TOKEN.
    max_cost_usd: optional hard cap per run; keywords past it come back as 'skipped' and are not charged.
    """

    def __init__(self, token: Optional[str] = None, max_cost_usd: Optional[float] = None, client: Any = None):
        if client is None:
            token = token or os.environ.get("APIFY_TOKEN")
            if not token:
                raise TrendsError("Pass token=... or set APIFY_TOKEN (Apify Console -> Settings -> API & Integrations).")
            from apify_client import ApifyClient
            client = ApifyClient(token)
        self._client = client
        self.max_cost_usd = max_cost_usd

    def lookup(self, keywords: Iterable[str], geo: str = "", timeframe: str = "today 12-m", search_type: str = "web",
               category: int = 0, compare: bool = False, regions: bool = True, related_queries: bool = True,
               region_resolution: str = "auto", trends_urls: Iterable[str] = ()) -> TrendsResult:
        """Look up many keywords in one run. Each keyword is one lookup ($0.005); failed lookups are free.

        compare=True puts keywords on one 0-100 scale, in groups of up to 5 (Google's limit).
        """
        kws = [k for k in keywords if k and k.strip()]
        urls = list(trends_urls)
        if not kws and not urls:
            raise TrendsError("Give at least one keyword or Google Trends URL.")
        time_range, custom = _time_range(timeframe)
        run_input: dict[str, Any] = {
            "keywords": kws, "geo": geo, "timeRange": time_range, "searchType": _search_type(search_type),
            "category": int(category), "compareKeywords": bool(compare), "includeRegions": bool(regions),
            "includeRelatedQueries": bool(related_queries), "regionResolution": region_resolution,
        }
        if custom:
            run_input["customTimeRange"] = custom
        if urls:
            run_input["trendsUrls"] = urls
        call_kwargs = {"run_input": run_input}
        if self.max_cost_usd is not None:
            call_kwargs["max_total_charge_usd"] = Decimal(str(self.max_cost_usd))
        run = self._client.actor(ACTOR_ID).call(**call_kwargs)
        if run is None:
            raise TrendsError("The run did not finish (timed out waiting).")
        dataset_id = getattr(run, "default_dataset_id", None) or (run.get("defaultDatasetId") if isinstance(run, dict) else None)
        status = getattr(run, "status", None) or (run.get("status") if isinstance(run, dict) else None)
        status = getattr(status, "value", status)        # apify-client 3.x returns an enum
        rows = list(self._client.dataset(dataset_id).iterate_items()) if dataset_id else []
        if status not in (None, "SUCCEEDED") and not rows:
            raise TrendsError(f"Run ended with status {status}.")
        return TrendsResult(rows)


class TrendReq:
    """pytrends-compatible interface. Replace `from pytrends.request import TrendReq` with
    `from google_trends_api import TrendReq` and pass your Apify token.

    pytrends arguments that only tuned its own HTTP session (hl, tz, timeout, proxies, retries, backoff_factor,
    requests_args) are accepted and ignored: proxies and retries run inside the hosted Actor.
    """

    def __init__(self, hl: str = "en-US", tz: int = 360, apify_token: Optional[str] = None,
                 max_cost_usd: Optional[float] = None, client: Any = None, **_ignored: Any):
        self._gt = GoogleTrends(token=apify_token, max_cost_usd=max_cost_usd, client=client)
        self._payload: Optional[dict] = None
        self._cache: dict[tuple, TrendsResult] = {}

    def build_payload(self, kw_list: list[str], cat: int = 0, timeframe: str = "today 5-y", geo: str = "",
                      gprop: str = "") -> None:
        if not kw_list or len(kw_list) > 5:
            raise TrendsError("kw_list takes 1 to 5 keywords, as in pytrends. For bulk lists use GoogleTrends.lookup().")
        _time_range(timeframe)
        _search_type(gprop)
        self._payload = {"keywords": list(kw_list), "category": cat, "timeframe": timeframe, "geo": geo,
                         "search_type": gprop}

    def _result(self, resolution: str = "auto") -> TrendsResult:
        if self._payload is None:
            raise TrendsError("Call build_payload() first.")
        p = self._payload
        key = (tuple(p["keywords"]), p["category"], p["timeframe"], p["geo"], p["search_type"], resolution)
        if key not in self._cache:
            # Several keywords in one payload are compared on one scale, as in pytrends.
            self._cache[key] = self._gt.lookup(compare=len(p["keywords"]) > 1, region_resolution=resolution, **p)
        return self._cache[key]

    def interest_over_time(self):
        return self._result().interest_over_time()

    def interest_by_region(self, resolution: str = "COUNTRY", inc_low_vol: bool = False, inc_geo_code: bool = False):
        if resolution == "CITY":
            raise TrendsError("City-level data isn't available: Google withholds it from automated lookups.")
        if resolution not in RESOLUTIONS:
            raise TrendsError(f"resolution must be one of {sorted(RESOLUTIONS)}.")
        # Google's default level (countries worldwide, states/regions inside a country) is what COUNTRY and REGION
        # return in pytrends, so both reuse the run interest_over_time() already paid for. Only DMA needs its own.
        return self._result("DMA" if resolution == "DMA" else "auto").interest_by_region()

    def related_queries(self) -> dict:
        return self._result().related_queries()

    def related_topics(self):
        raise TrendsError("Related topics aren't available: Google withholds them from automated lookups "
                          "(including real browsers). Use related_queries().")

    def summary(self):
        """Not in pytrends: one row per keyword with momentum, year-on-year change, peak and seasonality."""
        return self._result().summary()
