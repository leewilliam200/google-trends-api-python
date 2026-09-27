"""Which products are seasonal, and when do they peak? Needs APIFY_TOKEN in the environment."""
from google_trends_api import GoogleTrends

res = GoogleTrends(max_cost_usd=0.10).lookup(
    ["halloween costume", "pool float", "ski jacket", "sunscreen", "air conditioner"],
    geo="US",
    timeframe="today 5-y",
)
print(res.summary()[["momentum", "yearOnYearChangePct", "seasonal", "seasonalPeakMonth", "topRisingQuery"]])
