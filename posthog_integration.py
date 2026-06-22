# =============================================================================
# JewelScope Research — PostHog Analytics Integration
# =============================================================================
#
# Pushes jewelry market intelligence events to PostHog for real-time
# dashboards, trend tracking, and alerting.
#
# PostHog API: https://app.posthog.com/project/<id>/settings → Project API Key
# Free tier: 1 million events/month
#
# Set environment variable: POSTHOG_API_KEY
# Or pass directly: PostHogClient(api_key="phc_...")
# =============================================================================

import os
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY", "")
POSTHOG_API_URL = "https://app.posthog.com/capture/"
POSTHOG_UI_URL = "https://app.posthog.com"


class PostHogClient:
    """
    Sends jewelry market intelligence events to PostHog.
    
    Uses PostHog's /capture API endpoint (no SDK needed).
    Each event becomes queryable in PostHog Trends, Funnels, and Dashboards.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or POSTHOG_API_KEY
        if not self.api_key:
            logger.warning("No POSTHOG_API_KEY set — PostHog integration disabled")
        self.enabled = bool(self.api_key)
        self.stats = {"events_sent": 0, "errors": 0, "last_error": ""}

    def _capture(self, event: str, properties: dict = None,
                 distinct_id: str = "jewelscope") -> bool:
        """
        Send a single event to PostHog.
        
        Args:
            event: Event name (e.g., "fine_jewelry_scan_completed")
            properties: Dict of event properties
            distinct_id: Identifier for the source (default: "jewelscope")
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        payload = {
            "api_key": self.api_key,
            "event": event,
            "distinct_id": distinct_id,
            "properties": properties or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            resp = httpx.post(
                POSTHOG_API_URL,
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                self.stats["events_sent"] += 1
                return True
            else:
                logger.warning(f"PostHog API returned {resp.status_code}: {resp.text[:200]}")
                self.stats["errors"] += 1
                self.stats["last_error"] = f"HTTP {resp.status_code}"
                return False
        except Exception as e:
            logger.warning(f"PostHog send error: {e}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return False

    def send_scan_completed(self, insights: dict) -> bool:
        """
        Send a fine jewelry scan completed event with market summary.
        
        Creates a PostHog event that can power:
        - Time-series chart of avg listing price over time
        - Total shops/listings tracked over time
        - Market value growth tracking
        """
        return self._capture(
            event="fine_jewelry_scan_completed",
            properties={
                "total_shops_tracked": insights.get("total_shops_tracked", 0),
                "total_listings_collected": insights.get("total_listings_collected", 0),
                "avg_listing_price": round(insights.get("avg_listing_price", 0), 2),
                "total_market_value": round(insights.get("total_market_value", 0), 2),
                "avg_shop_listings": round(insights.get("avg_shop_listings", 0), 1),
                "scan_date": insights.get("scan_date", date.today().isoformat()),
                "shops_by_category": json.dumps(insights.get("shops_by_category", {})),
                "shops_by_tier": json.dumps(insights.get("shops_by_tier", {})),
            }
        )

    def send_gold_karat_trends(self, gold_karat_trends: dict) -> int:
        """
        Send individual gold karat trend events.
        
        Each karat type becomes a separate event, allowing PostHog to
        chart 14K vs 18K vs 24K popularity over time.
        """
        count = 0
        for karat, data in gold_karat_trends.items():
            ok = self._capture(
                event="gold_karat_trend",
                properties={
                    "karat": karat,
                    "listing_count": data.get("count", 0),
                    "avg_price": round(data.get("avg_price", 0), 2),
                    "total_views": data.get("total_views", 0),
                    "total_favorites": data.get("total_favorites", 0),
                    "scan_date": date.today().isoformat(),
                },
                distinct_id=f"jewelscope_gold_{karat.lower().replace(' ', '_')}",
            )
            if ok:
                count += 1
        return count

    def send_gemstone_trends(self, top_gemstones: list) -> int:
        """
        Send gemstone trend events.
        
        Each gemstone becomes an event, letting PostHog chart
        diamond vs sapphire vs moissanite demand over weeks.
        """
        count = 0
        for g in top_gemstones[:10]:
            ok = self._capture(
                event="gemstone_trend",
                properties={
                    "gemstone": g.get("gemstone", ""),
                    "listing_count": g.get("count", 0),
                    "avg_price": round(g.get("avg_price", 0), 2),
                    "total_sold": g.get("total_sold", 0),
                    "engagement_rate": round(g.get("engagement_rate", 0), 1),
                    "scan_date": date.today().isoformat(),
                },
                distinct_id=f"jewelscope_gem_{g.get('gemstone', 'unknown').lower()}",
            )
            if ok:
                count += 1
        return count

    def send_shop_rankings(self, shop_rankings: list) -> int:
        """
        Send top shop ranking events.
        
        Enables PostHog dashboards for:
        - Top 10 shops by engagement this week
        - Shop conversion rate comparison
        - Average price by shop
        """
        count = 0
        for s in shop_rankings[:10]:
            ok = self._capture(
                event="shop_ranking",
                properties={
                    "shop_name": s.get("shop_name", ""),
                    "total_listings": s.get("total_listings", 0),
                    "total_views": s.get("total_views", 0),
                    "total_favorites": s.get("total_favorites", 0),
                    "total_sold": s.get("total_sold", 0),
                    "total_engagement": s.get("total_engagement", 0),
                    "avg_price": round(s.get("avg_price", 0), 2),
                    "engagement_per_listing": round(s.get("engagement_per_listing", 0), 1),
                    "conversion_rate": round(s.get("conversion_rate", 0), 2),
                    "scan_date": date.today().isoformat(),
                },
                distinct_id=f"jewelscope_shop_{s.get('shop_name', 'unknown').lower().replace(' ', '_')}",
            )
            if ok:
                count += 1
        return count

    def send_category_leaders(self, category_leaders: dict) -> int:
        """Send category leader events for each jewelry category."""
        count = 0
        for category, data in category_leaders.items():
            ok = self._capture(
                event="category_leader",
                properties={
                    "category": category,
                    "top_shop": data.get("top_shop", ""),
                    "total_shops": data.get("total_shops", 0),
                    "avg_shop_price": round(data.get("avg_shop_price", 0), 2),
                    "top_engagement": data.get("top_engagement", 0),
                    "total_listings": data.get("total_listings", 0),
                    "scan_date": date.today().isoformat(),
                },
                distinct_id=f"jewelscope_cat_{category}",
            )
            if ok:
                count += 1
        return count

    def send_all_fine_jewelry_insights(self, insights: dict) -> dict:
        """
        Send all fine jewelry insights as PostHog events in one call.
        
        Returns:
            Dict with counts of events sent per category
        """
        if not self.enabled:
            return {"enabled": False, "message": "PostHog API key not configured"}

        results = {}

        # 1. Scan summary
        results["scan_completed"] = 1 if self.send_scan_completed(insights) else 0

        # 2. Gold karat trends
        gold = insights.get("gold_karat_trends", {})
        results["gold_karat_trends"] = self.send_gold_karat_trends(gold)

        # 3. Gemstone trends
        gems = insights.get("top_gemstones", [])
        results["gemstone_trends"] = self.send_gemstone_trends(gems)

        # 4. Shop rankings
        shops = insights.get("shop_rankings", [])
        results["shop_rankings"] = self.send_shop_rankings(shops)

        # 5. Category leaders
        cats = insights.get("category_leaders", {})
        results["category_leaders"] = self.send_category_leaders(cats)

        total = sum(results.values())
        logger.info(f"PostHog: {total} events sent ({results})")
        return results

    def get_dashboard_url(self) -> str:
        """Get the PostHog dashboard URL for quick access."""
        return f"{POSTHOG_UI_URL}/project/insights"

    def format_results_summary(self, results: dict) -> str:
        """Format event send results as a readable summary."""
        if not results.get("enabled", True):
            return "📡 PostHog: ⏸️ Not configured (set POSTHOG_API_KEY)"

        total = sum(v for k, v in results.items() if isinstance(v, int))
        parts = []
        for key, val in results.items():
            if isinstance(val, int) and val > 0:
                label = key.replace("_", " ").title()
                parts.append(f"{label}: {val}")
        if parts:
            return f"📡 PostHog: ✅ {total} events sent ({', '.join(parts)})"
        return "📡 PostHog: ⚠️ No events sent"