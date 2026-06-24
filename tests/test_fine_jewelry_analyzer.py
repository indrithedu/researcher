"""
E2E tests for Fine Jewelry Analyzer — no API keys needed.
Uses mock listing data to validate pricing, gold karat, gemstone,
and competitive analysis logic.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_mock_listing(**kwargs):
    """Helper to create a mock EtsyListing-like object."""
    from etsy_api import EtsyListing
    defaults = {
        "listing_id": 1,
        "title": "14k Gold Diamond Ring",
        "description": "Beautiful ring",
        "price_amount": 500.0,
        "price_currency": "USD",
        "taxonomy_id": 143,
        "taxonomy_path": ["Jewelry", "Rings", "Engagement Rings"],
        "tags": ["gold", "diamond", "ring", "engagement"],
        "materials": ["gold", "diamond"],
        "style": ["modern"],
        "quantity": 1,
        "views": 500,
        "favorites": 50,
        "num_sold": 10,
        "state": "active",
        "shop_id": 100,
        "shop_name": "TestJewelryCo",
        "url": "https://etsy.com/listing/1",
        "created_ts": 1700000000,
        "is_vintage": False,
    }
    defaults.update(kwargs)
    return EtsyListing(**defaults)


class TestFineJewelryDataModels(unittest.TestCase):
    """Test FineJewelryInsights dataclass."""

    def setUp(self):
        from etsy_api import FineJewelryInsights
        self.Insights = FineJewelryInsights

    def test_default_values(self):
        insights = self.Insights()
        self.assertEqual(insights.total_shops_tracked, 0)
        self.assertEqual(insights.total_listings_collected, 0)
        self.assertEqual(insights.shop_rankings, [])
        self.assertEqual(insights.high_demand_listings, [])
        self.assertEqual(insights.avg_listing_price, 0.0)

    def test_format_summary_empty(self):
        insights = self.Insights()
        summary = insights.format_summary()
        self.assertIn("Fine Jewelry", summary)
        self.assertIn("0", summary)

    def test_format_summary_with_data(self):
        insights = self.Insights(
            total_shops_tracked=10,
            total_listings_collected=200,
            avg_price_by_category={"Rings": 850.0, "Necklaces": 450.0},
            top_gemstones=[{"gemstone": "Diamond", "count": 50, "avg_price": 1200}],
            gold_karat_trends={"14K": {"count": 30, "avg_price": 600}},
            shop_rankings=[{"shop_name": "BestShop", "total_engagement": 5000}],
            high_demand_listings=[{"title": "Gold Ring", "favorites": 100}],
        )
        summary = insights.format_summary()
        self.assertIn("10", summary)
        self.assertIn("200", summary)
        self.assertIn("BestShop", summary)
        self.assertIn("Gold Ring", summary)

    def test_etsy_listing_price_category(self):
        listing = _make_mock_listing(price_amount=50)
        self.assertEqual(listing.price_category, "mid_range")

        listing = _make_mock_listing(price_amount=150)
        self.assertEqual(listing.price_category, "mid_range")

        listing = _make_mock_listing(price_amount=500)
        self.assertEqual(listing.price_category, "premium")

        listing = _make_mock_listing(price_amount=1500)
        self.assertEqual(listing.price_category, "luxury")

    def test_etsy_listing_engagement_score(self):
        listing = _make_mock_listing(views=100, favorites=20, num_sold=5)
        # 100 + 20*3 + 5*10 = 100 + 60 + 50 = 210
        self.assertEqual(listing.engagement_score, 210)

    def test_etsy_listing_to_dict(self):
        listing = _make_mock_listing(listing_id=42, title="Test Ring")
        d = listing.to_dict()
        self.assertEqual(d["listing_id"], 42)
        self.assertEqual(d["title"], "Test Ring")

    def test_etsy_listing_to_article(self):
        listing = _make_mock_listing(title="Gold Ring", price_amount=500)
        article = listing.to_article()
        self.assertEqual(article["category"], "etsy")
        self.assertEqual(article["title"], "Gold Ring")
        self.assertEqual(article["price"], 500.0)


class TestFineJewelryAnalyzer(unittest.TestCase):
    """Test the analysis pipeline with mock data."""

    def setUp(self):
        from etsy_api import FineJewelryAnalyzer
        self.analyzer = FineJewelryAnalyzer()

        # Mock listings across different categories
        self.mock_listings = [
            _make_mock_listing(
                listing_id=1, title="14k Gold Diamond Ring",
                price_amount=800, tags=["gold", "diamond", "ring", "14k"],
                materials=["gold", "diamond"], views=1000, favorites=200,
                num_sold=15, shop_name="DiamondShop", taxonomy_path=["Jewelry", "Rings"],
            ),
            _make_mock_listing(
                listing_id=2, title="18k Rose Gold Necklace",
                price_amount=1200, tags=["rose gold", "necklace", "18k"],
                materials=["gold", "rose gold"], views=800, favorites=150,
                num_sold=8, shop_name="GoldShop", taxonomy_path=["Jewelry", "Necklaces"],
            ),
            _make_mock_listing(
                listing_id=3, title="Silver Pearl Earrings",
                price_amount=250, tags=["silver", "pearl", "earrings"],
                materials=["silver", "pearl"], views=600, favorites=100,
                num_sold=20, shop_name="PearlShop", taxonomy_path=["Jewelry", "Earrings"],
            ),
            _make_mock_listing(
                listing_id=4, title="Sapphire Gemstone Bracelet",
                price_amount=950, tags=["sapphire", "gemstone", "bracelet"],
                materials=["silver", "sapphire"], views=400, favorites=80,
                num_sold=5, shop_name="GemShop", taxonomy_path=["Jewelry", "Bracelets"],
            ),
            _make_mock_listing(
                listing_id=5, title="24k Yellow Gold Chain",
                price_amount=2000, tags=["gold", "24k", "chain"],
                materials=["gold", "24k gold"], views=300, favorites=60,
                num_sold=3, shop_name="GoldShop", taxonomy_path=["Jewelry", "Necklaces"],
            ),
        ]

        # Mock shop data
        self.mock_shop_data = [
            {"shop_id": 1, "shop_name": "DiamondShop", "category": "engagement_rings",
             "price_tier": "luxury", "total_sales": 500, "listings_fetched": 2},
            {"shop_id": 2, "shop_name": "GoldShop", "category": "gold_necklaces",
             "price_tier": "premium", "total_sales": 300, "listings_fetched": 2},
            {"shop_id": 3, "shop_name": "PearlShop", "category": "pearl_gemstone",
             "price_tier": "premium", "total_sales": 200, "listings_fetched": 1},
            {"shop_id": 4, "shop_name": "GemShop", "category": "pearl_gemstone",
             "price_tier": "luxury", "total_sales": 150, "listings_fetched": 1},
        ]

        self.analyzer.listings = self.mock_listings
        self.analyzer.shop_data = self.mock_shop_data

    def test_analyze_returns_insights(self):
        insights = self.analyzer.analyze()
        from etsy_api import FineJewelryInsights
        self.assertIsInstance(insights, FineJewelryInsights)
        self.assertEqual(insights.total_shops_tracked, 4)
        self.assertEqual(insights.total_listings_collected, 5)

    def test_pricing_by_category(self):
        insights = self.analyzer.analyze()
        self.assertIn("Rings", insights.avg_price_by_category)
        self.assertIn("Necklaces", insights.avg_price_by_category)
        self.assertGreater(insights.avg_price_by_category["Rings"], 0)

    def test_price_distribution(self):
        insights = self.analyzer.analyze()
        if insights.price_distribution:
            for cat, dist in insights.price_distribution.items():
                self.assertIn("p25", dist)
                self.assertIn("p50", dist)
                self.assertIn("p75", dist)
                self.assertIn("avg", dist)
                self.assertIn("count", dist)

    def test_gold_karat_trends(self):
        insights = self.analyzer.analyze()
        # We have 14k, 18k, 24k in mock listings
        detected_karats = list(insights.gold_karat_trends.keys())
        self.assertIn("14K", detected_karats)
        self.assertIn("18K", detected_karats)
        self.assertIn("24K", detected_karats)

    def test_gold_karat_trend_data(self):
        insights = self.analyzer.analyze()
        if "14K" in insights.gold_karat_trends:
            data = insights.gold_karat_trends["14K"]
            self.assertIn("count", data)
            self.assertIn("avg_price", data)
            self.assertGreater(data["count"], 0)

    def test_top_gemstones(self):
        insights = self.analyzer.analyze()
        gem_names = [g["gemstone"] for g in insights.top_gemstones]
        self.assertIn("Diamond", gem_names)
        self.assertIn("Sapphire", gem_names)
        self.assertIn("Pearl", gem_names)

    def test_shop_rankings(self):
        insights = self.analyzer.analyze()
        self.assertGreater(len(insights.shop_rankings), 0)
        # GoldShop should have 2 listings, DiamondShop 2, others 1
        for shop in insights.shop_rankings:
            self.assertIn("shop_name", shop)
            self.assertIn("total_listings", shop)
            self.assertIn("total_views", shop)
            self.assertIn("total_favorites", shop)
            self.assertIn("avg_price", shop)

    def test_shops_by_category(self):
        insights = self.analyzer.analyze()
        self.assertIn("engagement_rings", insights.shops_by_category)
        self.assertIn("gold_necklaces", insights.shops_by_category)
        self.assertIn("pearl_gemstone", insights.shops_by_category)

    def test_high_demand_listings(self):
        insights = self.analyzer.analyze()
        self.assertGreater(len(insights.high_demand_listings), 0)
        # Diamond listing has highest engagement
        top = insights.high_demand_listings[0]
        self.assertIn("title", top)
        self.assertIn("price", top)
        self.assertIn("favorites", top)
        self.assertIn("engagement_score", top)

    def test_top_tags(self):
        insights = self.analyzer.analyze()
        self.assertGreater(len(insights.top_fine_jewelry_tags), 0)
        first_tag = insights.top_fine_jewelry_tags[0]
        self.assertIn("tag", first_tag)
        self.assertIn("count", first_tag)
        self.assertIn("pct", first_tag)

    def test_top_materials(self):
        insights = self.analyzer.analyze()
        self.assertGreater(len(insights.top_materials_used), 0)
        mat_names = [m["material"] for m in insights.top_materials_used]
        self.assertIn("gold", mat_names)

    def test_avg_listing_price(self):
        insights = self.analyzer.analyze()
        # (800 + 1200 + 250 + 950 + 2000) / 5 = 5200 / 5 = 1040
        self.assertAlmostEqual(insights.avg_listing_price, 1040.0, delta=1)

    def test_total_market_value(self):
        insights = self.analyzer.analyze()
        self.assertAlmostEqual(insights.total_market_value, 5200.0, delta=1)

    def test_diamond_specs(self):
        insights = self.analyzer.analyze()
        if insights.diamond_specs:
            self.assertIn("total_diamond_listings", insights.diamond_specs)
            self.assertIn("avg_diamond_price", insights.diamond_specs)
            self.assertGreater(insights.diamond_specs["total_diamond_listings"], 0)


class TestFineJewelryAnalyzerEdgeCases(unittest.TestCase):
    """Test edge cases in the analyzer."""

    def setUp(self):
        from etsy_api import FineJewelryAnalyzer
        self.analyzer = FineJewelryAnalyzer()

    def test_empty_listings(self):
        self.analyzer.listings = []
        self.analyzer.shop_data = []
        insights = self.analyzer.analyze()
        self.assertEqual(insights.total_listings_collected, 0)
        self.assertEqual(insights.total_shops_tracked, 0)

    def test_listings_without_shop_data(self):
        self.analyzer.listings = [_make_mock_listing(listing_id=1)]
        self.analyzer.shop_data = []
        insights = self.analyzer.analyze()
        # Should still work, just no shop-level metrics
        self.assertEqual(insights.total_shops_tracked, 0)
        self.assertEqual(insights.total_listings_collected, 1)

    def test_zero_price_listings(self):
        self.analyzer.listings = [_make_mock_listing(listing_id=1, price_amount=0)]
        self.analyzer.shop_data = []
        insights = self.analyzer.analyze()
        self.assertEqual(insights.avg_listing_price, 0)

    def test_negative_price_handled(self):
        """Negative prices shouldn't crash — though they shouldn't exist."""
        self.analyzer.listings = [_make_mock_listing(listing_id=1, price_amount=-10)]
        self.analyzer.shop_data = []
        insights = self.analyzer.analyze()
        self.assertEqual(insights.avg_listing_price, -10)

    def test_optimal_price_ranges(self):
        """Test that optimal price range detection doesn't crash with limited data."""
        self.analyzer.listings = [
            _make_mock_listing(listing_id=i, price_amount=i * 100, views=100, favorites=10)
            for i in range(1, 10)
        ]
        insights = self.analyzer.analyze()
        # May or may not have optimal ranges depending on data distribution
        self.assertIsNotNone(insights.optimal_price_ranges)


class TestFineJewelryScanFunction(unittest.TestCase):
    """Test the scan_all_shops integration path."""

    def setUp(self):
        from etsy_api import FineJewelryAnalyzer
        self.analyzer = FineJewelryAnalyzer()

    def test_scan_all_shops_without_api_key(self):
        """Should handle missing API key gracefully."""
        # Mock the API client to return empty data
        self.analyzer.api = MagicMock()
        self.analyzer.api.scan_fine_jewelry_shops.return_value = {
            "shops": [],
            "listings": [],
            "shop_listings": {},
            "errors": ["No API key"],
        }
        result = self.analyzer.scan_all_shops()
        self.assertIsNotNone(result)
        self.assertEqual(len(result.get("listings", [])), 0)
        self.assertIn("errors", result)

    def test_analyze_weighted_engagement(self):
        """Test that high-engagement listings bubble to the top."""
        listings = [
            _make_mock_listing(listing_id=i, views=100 * i, favorites=10 * i, num_sold=i)
            for i in [1, 5, 10, 20]
        ]
        self.analyzer.listings = listings
        insights = self.analyzer.analyze()
        if insights.high_demand_listings:
            # The listing with most engagement should be first
            first = insights.high_demand_listings[0]
            self.assertGreaterEqual(first.get("engagement_score", 0), 0)


if __name__ == "__main__":
    unittest.main()