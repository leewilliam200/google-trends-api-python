"""Offline tests: a fake Apify client replays rows shaped like the Actor's real output."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from google_trends_api import GoogleTrends, TrendReq, TrendsError


def row(keyword, status="ok", peak=100):
    return {
        "keyword": keyword, "status": status, "geo": "US", "timeRange": "past_5_years",
        "summary": {"momentum": "rising", "yearOnYearChangePct": 12, "seasonal": True, "seasonalPeakMonth": "October",
                    "topRisingQuery": f"{keyword} deals", "text": f"{keyword} is rising."},
        "interestOverTime": [{"date": "2026-08-30", "value": peak // 2, "isPartial": False},
                             {"date": "2026-09-06", "value": peak, "isPartial": True}],
        "interestByRegion": [{"geoCode": "US-CA", "geoName": "California", "value": 100},
                             {"geoCode": "US-TX", "geoName": "Texas", "value": 80}],
        "relatedQueries": {"top": [{"query": f"best {keyword}", "value": 100, "sharesWordWithKeyword": True}],
                           "rising": [{"query": f"{keyword} deals", "growth": "+350%", "growthPct": 350,
                                       "sharesWordWithKeyword": True},
                                      {"query": "laptop stand", "growth": "Breakout", "growthPct": None,
                                       "sharesWordWithKeyword": False}]},
    }


class FakeClient:
    def __init__(self, rows=None, status="SUCCEEDED"):
        self.calls, self.rows, self.status = [], rows, status

    def actor(self, actor_id):
        fake = self

        class _Actor:
            def call(self, **kwargs):
                fake.calls.append((actor_id, kwargs))
                return SimpleNamespace(default_dataset_id="ds1", status=SimpleNamespace(value=fake.status))
        return _Actor()

    def dataset(self, dataset_id):
        rows = self.rows if self.rows is not None else [row(k) for k in self.calls[-1][1]["run_input"]["keywords"]]

        class _Dataset:
            def iterate_items(self):
                return iter(rows)
        return _Dataset()


def test_lookup_maps_pytrends_arguments_to_actor_input():
    fake = FakeClient()
    GoogleTrends(client=fake, max_cost_usd=0.5).lookup(["air fryer", "vpn"], geo="US", timeframe="today 5-y",
                                                        search_type="froogle")
    actor_id, kwargs = fake.calls[0]
    assert actor_id == "meridianlabs/google-trends-scraper"
    inp = kwargs["run_input"]
    assert inp["keywords"] == ["air fryer", "vpn"] and inp["timeRange"] == "past_5_years"
    assert inp["searchType"] == "shopping" and inp["geo"] == "US" and inp["compareKeywords"] is False
    assert kwargs["max_total_charge_usd"] == Decimal("0.5")


def test_custom_timeframe_and_actor_names_accepted():
    fake = FakeClient()
    gt = GoogleTrends(client=fake)
    gt.lookup(["x"], timeframe="2024-01-01 2025-06-30")
    assert fake.calls[-1][1]["run_input"]["timeRange"] == "custom"
    assert fake.calls[-1][1]["run_input"]["customTimeRange"] == "2024-01-01 2025-06-30"
    gt.lookup(["x"], timeframe="past_90_days", search_type="youtube")
    assert fake.calls[-1][1]["run_input"]["timeRange"] == "past_90_days"


@pytest.mark.parametrize("bad", [{"timeframe": "today 2-y"}, {"search_type": "maps"}])
def test_bad_arguments_raise_before_any_run(bad):
    fake = FakeClient()
    with pytest.raises(TrendsError):
        GoogleTrends(client=fake).lookup(["x"], **bad)
    assert fake.calls == []


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(TrendsError):
        GoogleTrends()


def test_dataframes_have_pytrends_shape():
    res = GoogleTrends(client=FakeClient()).lookup(["air fryer", "vpn"])
    iot = res.interest_over_time()
    assert list(iot.columns) == ["air fryer", "vpn", "isPartial"]
    assert iot["isPartial"].tolist() == [False, True]
    assert list(res.interest_by_region().index) == ["California", "Texas"]
    rq = res.related_queries()["air fryer"]
    assert rq["top"]["query"].tolist() == ["best air fryer"]
    assert rq["rising"]["value"].tolist()[0] == 350
    assert rq["rising"]["growth"].tolist()[1] == "Breakout"
    assert res.summary().loc["vpn", "momentum"] == "rising"


def test_no_data_rows_are_kept_but_left_out_of_frames():
    res = GoogleTrends(client=FakeClient(rows=[row("air fryer"), {"keyword": "zqxv", "status": "no_data"}])).lookup(
        ["air fryer", "zqxv"])
    assert len(res) == 2 and len(res.ok()) == 1
    assert list(res.interest_over_time().columns) == ["air fryer", "isPartial"]


def test_trendreq_is_a_drop_in_and_runs_once():
    fake = FakeClient()
    pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25), retries=2, client=fake)
    pytrends.build_payload(["air fryer", "vpn"], timeframe="today 12-m", geo="US")
    pytrends.interest_over_time()
    pytrends.interest_by_region()
    pytrends.interest_by_region(resolution="REGION")
    pytrends.related_queries()
    assert len(fake.calls) == 1                                  # one paid run serves all four calls
    assert fake.calls[0][1]["run_input"]["compareKeywords"] is True
    pytrends.interest_by_region(resolution="DMA")
    assert len(fake.calls) == 2 and fake.calls[1][1]["run_input"]["regionResolution"] == "DMA"


def test_trendreq_limits_match_pytrends():
    pytrends = TrendReq(client=FakeClient())
    with pytest.raises(TrendsError):
        pytrends.interest_over_time()                            # no payload yet
    with pytest.raises(TrendsError):
        pytrends.build_payload(["a", "b", "c", "d", "e", "f"])
    pytrends.build_payload(["a"])
    with pytest.raises(TrendsError):
        pytrends.interest_by_region(resolution="CITY")
    with pytest.raises(TrendsError):
        pytrends.related_topics()


def test_failed_run_without_rows_raises():
    with pytest.raises(TrendsError):
        GoogleTrends(client=FakeClient(rows=[], status="FAILED")).lookup(["x"])
