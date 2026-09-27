"""Google Trends API for Python: a maintained pytrends alternative, hosted on Apify.

    from google_trends_api import TrendReq          # pytrends-compatible
    from google_trends_api import GoogleTrends      # bulk lookups

Data source: Google Trends (https://www.google.com/trends). Not affiliated with or endorsed by Google.
"""
from .client import ACTOR_ID, GoogleTrends, TrendReq, TrendsError, TrendsResult

__all__ = ["ACTOR_ID", "GoogleTrends", "TrendReq", "TrendsError", "TrendsResult"]
__version__ = "0.1.0"
