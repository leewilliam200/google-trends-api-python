"""pytrends code, one import changed. Needs APIFY_TOKEN in the environment."""
from google_trends_api import TrendReq

pytrends = TrendReq(hl="en-US", tz=360)
pytrends.build_payload(["air fryer", "standing desk"], timeframe="today 12-m", geo="US")

print(pytrends.interest_over_time().tail())
print(pytrends.interest_by_region().head())
for keyword, frames in pytrends.related_queries().items():
    print(keyword, "rising:", frames["rising"].head(3).to_dict("records") if frames["rising"] is not None else None)
