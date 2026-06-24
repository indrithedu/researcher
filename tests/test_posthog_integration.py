"""
E2E tests for PostHog integration — no real API key needed.
Tests event formatting, batching, and graceful fallback.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPostHogClientInit(unittest.TestCase):
    """Test PostHog client initialization."""

    def test_disabled_without_key(self):
        from posthog_integration import PostHogClient
        client = PostHogClient(api_key="")
        self.assertFalse(client.enabled)

    def test_enabled_with_key(self):
        from posthog_integration import PostHogClient
        client = PostHogClient(api_key="phc_test123")
        self.assertTrue(client.enabled)

    def test_env_var_fallback(self):
        with patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_env_test"}):
            from posthog_integration import PostHogClient
            client = PostHogClient()
            self.assertTrue(client.enabled)
            self.assertEqual(client.api_key, "phc_env_test")


class TestPostHogEventSending(unittest.TestCase):
    """Test event formatting and sending."""

    def setUp(self):
        from posthog_integration import PostHogClient
        self.client = PostHogClient(api_key="phc_test123")

    @patch("posthog_integration.httpx.post")
    def test_capture_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = self.client._capture(
            event="test_event",
            properties={"key": "value"},
            distinct_id="test_id",
        )
        self.assertTrue(result)
        self.assertEqual(self.client.stats["events_sent"], 1)

    @patch("posthog_integration.httpx.post")
    def test_capture_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad request"
        mock_post.return_value = mock_resp

        result = self.client._capture(
            event="test_event",
            properties={},
        )
        self.assertFalse(result)
        self.assertEqual(self.client.stats["errors"], 1)

    @patch("posthog_integration.httpx.post")
    def test_capture_timeout(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")

        result = self.client._capture(
            event="test_event",
            properties={},
        )
        self.assertFalse(result)
        self.assertEqual(self.client.stats["errors"], 1)

    def test_send_disabled(self):
        client_empty = self.__class__(self._testMethodName)
        # Re-init with no key
        from posthog_integration import PostHogClient
        client = PostHogClient(api_key="")
        result = client.send_scan_completed({"total_shops_tracked": 5})
        self.assertFalse(result)


class TestPostHogFineJewelryEvents(unittest.TestCase):
    """Test fine jewelry-specific event formatting."""
    # Import at class level for decorators
    from posthog_integration import PostHogClient as _PH

    def setUp(self):
        from posthog_integration import PostHogClient
        self.client = PostHogClient(api_key="phc_test123")

    @patch.object(_PH, '_capture', return_value=True)
    def test_send_scan_completed(self, mock_capture):
        insights = {
            "total_shops_tracked": 10,
            "total_listings_collected": 200,
            "avg_listing_price": 850.0,
            "total_market_value": 170000.0,
            "avg_shop_listings": 20.0,
            "scan_date": "2024-01-15",
            "shops_by_category": '{"engagement": 3, "necklaces": 2}',
            "shops_by_tier": '{"premium": 4, "luxury": 2}',
        }
        ok = self.client.send_scan_completed(insights)
        self.assertTrue(ok)
        mock_capture.assert_called_once()
        call_args = mock_capture.call_args[1]
        self.assertEqual(call_args["event"], "fine_jewelry_scan_completed")
        self.assertEqual(call_args["properties"]["total_shops_tracked"], 10)
        self.assertEqual(call_args["properties"]["avg_listing_price"], 850.0)

    @patch.object(_PH, '_capture', return_value=True)
    def test_send_gold_karat_trends(self, mock_capture):
        trends = {
            "14K": {"count": 20, "avg_price": 600.0, "total_views": 2000, "total_favorites": 300},
            "18K": {"count": 10, "avg_price": 1200.0, "total_views": 1500, "total_favorites": 200},
        }
        count = self.client.send_gold_karat_trends(trends)
        self.assertEqual(count, 2)
        self.assertEqual(mock_capture.call_count, 2)

    @patch.object(_PH, '_capture', return_value=True)
    def test_send_gemstone_trends(self, mock_capture):
        trends = [
            {"gemstone": "Diamond", "count": 25, "avg_price": 1500.0,
             "total_sold": 10, "engagement_rate": 85.0},
            {"gemstone": "Sapphire", "count": 15, "avg_price": 800.0,
             "total_sold": 5, "engagement_rate": 70.0},
            {"gemstone": "Ruby", "count": 5, "avg_price": 2000.0,
             "total_sold": 2, "engagement_rate": 90.0},
        ]
        count = self.client.send_gemstone_trends(trends)
        self.assertEqual(count, 3)

    @patch.object(_PH, '_capture', return_value=True)
    def test_send_shop_rankings(self, mock_capture):
        rankings = [
            {"shop_name": "BestShop", "total_listings": 20, "total_views": 5000,
             "total_favorites": 800, "total_sold": 100, "total_engagement": 10000,
             "avg_price": 900.0, "engagement_per_listing": 500.0, "conversion_rate": 2.0},
        ]
        count = self.client.send_shop_rankings(rankings)
        self.assertEqual(count, 1)

    @patch.object(_PH, '_capture', return_value=True)
    def test_send_category_leaders(self, mock_capture):
        leaders = {
            "engagement_rings": {"top_shop": "BestShop", "total_shops": 3,
                                 "avg_shop_price": 900.0, "top_engagement": 10000,
                                 "total_listings": 50},
        }
        count = self.client.send_category_leaders(leaders)
        self.assertEqual(count, 1)

    @patch.object(_PH, '_capture', return_value=True)
    def test_send_all_events(self, mock_capture):
        insights = {
            "total_shops_tracked": 5,
            "total_listings_collected": 100,
            "avg_listing_price": 750.0,
            "total_market_value": 75000.0,
            "avg_shop_listings": 20.0,
            "scan_date": "2024-01-15",
            "shops_by_category": '{}',
            "shops_by_tier": '{}',
            "gold_karat_trends": {"14K": {"count": 10, "avg_price": 500.0,
                                          "total_views": 1000, "total_favorites": 100}},
            "top_gemstones": [{"gemstone": "Diamond", "count": 5, "avg_price": 1500.0,
                               "total_sold": 2, "engagement_rate": 80.0}],
            "shop_rankings": [{"shop_name": "BestShop", "total_listings": 10,
                               "total_views": 2000, "total_favorites": 300,
                               "total_sold": 50, "total_engagement": 5000,
                               "avg_price": 750.0, "engagement_per_listing": 500.0,
                               "conversion_rate": 2.5}],
            "category_leaders": {"rings": {"top_shop": "BestShop", "total_shops": 2,
                                            "avg_shop_price": 750.0, "top_engagement": 5000,
                                            "total_listings": 20}},
        }
        results = self.client.send_all_fine_jewelry_insights(insights)
        self.assertIn("scan_completed", results)
        self.assertIn("gold_karat_trends", results)
        self.assertIn("gemstone_trends", results)
        self.assertIn("shop_rankings", results)
        self.assertIn("category_leaders", results)

    def test_format_results_summary(self):
        results = {
            "scan_completed": 1,
            "gold_karat_trends": 2,
            "gemstone_trends": 3,
            "shop_rankings": 1,
            "category_leaders": 1,
        }
        summary = self.client.format_results_summary(results)
        self.assertIn("events sent", summary)
        self.assertIn("8", summary)

    def test_format_results_summary_disabled(self):
        from posthog_integration import PostHogClient
        client = PostHogClient(api_key="")
        summary = client.format_results_summary({"enabled": False})
        self.assertIn("Not configured", summary)

    def test_get_dashboard_url(self):
        url = self.client.get_dashboard_url()
        self.assertIn("app.posthog.com", url)
        self.assertIn("insights", url)


if __name__ == "__main__":
    unittest.main()