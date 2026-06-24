"""
E2E tests for report generator — no API keys needed.
Tests HTML report generation with various data inputs.
"""

import unittest
import sys
import os
import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestReportGenerator(unittest.TestCase):
    """Test report generation with mock data."""

    def setUp(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from report_generator import ReportGenerator
        self.config = {
            "app": {"name": "JewelScope", "report_dir": tempfile.mkdtemp()},
        }
        self.generator = ReportGenerator(self.config)

        self.sample_articles = [
            {
                "source_name": "JCK Online",
                "source_url": "https://jckonline.com",
                "title": "Gold Prices Reach New High",
                "url": "https://jckonline.com/gold-high",
                "published_date": "2024-01-15",
                "summary": "Gold prices surged to record levels this quarter.",
                "category": "jewelry",
                "is_headline": True,
            },
            {
                "source_name": "Etsy Blog",
                "source_url": "https://etsy.com",
                "title": "Top Jewelry Trends for 2024",
                "url": "https://etsy.com/trends",
                "published_date": "2024-01-14",
                "summary": "Dainty jewelry continues to dominate.",
                "category": "etsy",
                "is_headline": False,
            },
        ]

        self.sample_headlines = [
            {
                "source_name": "National Jeweler",
                "source_url": "https://nationaljeweler.com",
                "title": "Diamond Market Overview",
                "url": "https://nationaljeweler.com/diamond",
                "published_date": "2024-01-15",
                "summary": "Lab-grown diamonds market share growing.",
                "category": "jewelry",
                "is_headline": True,
            },
        ]

        self.sample_etsy_intel = [
            {
                "source_name": "Etsy Seller Handbook",
                "title": "New SEO Features for Jewelry Sellers",
                "url": "https://etsy.com/seo",
                "summary": "Etsy rolls out new tagging system.",
            },
        ]

        self.sample_commodity_prices = [
            {
                "title": "Gold Price: $2,050.50/oz",
                "summary": "Up 1.2% today",
                "source_url": "https://kitco.com",
            },
        ]

        self.session_summary = {
            "sources_succeeded": 8,
            "sources_failed": 2,
            "total_articles": 45,
            "volatility_alerts": [
                {"commodity": "gold", "z_score": 2.5, "price": 2050.0, "type": "Surge"},
            ],
        }

    def test_generate_html_basic(self):
        """Test HTML generation with basic data."""
        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
        )
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))

        with open(path, "r") as f:
            content = f.read()
        self.assertIn("JewelScope", content)
        self.assertIn("Gold Prices", content)
        self.assertIn("Etsy", content)
        self.assertIn("Quick Scan", content)
        self.assertIn("Volatility", content)

    def test_generate_html_empty_data(self):
        """Test HTML generation with no data at all."""
        path = self.generator.generate_html(
            articles=[],
            headlines=[],
            etsy_intel=[],
            commodity_prices=[],
            session_summary={"sources_succeeded": 0, "sources_failed": 0,
                             "total_articles": 0, "volatility_alerts": []},
        )
        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("JewelScope", content)
        self.assertIn("0 articles", content)  # Stats show zero

    def test_generate_html_with_fine_jewelry(self):
        """Test with fine jewelry insights included."""
        fj_insights = {
            "total_shops_tracked": 5,
            "total_listings_collected": 50,
            "avg_listing_price": 850.0,
            "total_market_value": 42500.0,
            "shop_rankings": [
                {"shop_name": "BestShop", "total_listings": 20,
                 "avg_price": 900.0, "total_views": 5000,
                 "total_favorites": 800, "total_sold": 100,
                 "total_engagement": 10000, "conversion_rate": 2.0},
            ],
            "gold_karat_trends": {
                "14K": {"count": 20, "avg_price": 600.0,
                        "total_views": 2000, "total_favorites": 300},
                "18K": {"count": 15, "avg_price": 1200.0,
                        "total_views": 1500, "total_favorites": 200},
            },
            "top_gemstones": [
                {"gemstone": "Diamond", "count": 25, "avg_price": 1500.0},
                {"gemstone": "Sapphire", "count": 10, "avg_price": 800.0},
            ],
            "high_demand_listings": [
                {"title": "Gold Diamond Ring", "price": 1200.0,
                 "favorites": 200, "shop_name": "BestShop", "sold": 15},
            ],
            "top_fine_jewelry_tags": [
                {"tag": "gold", "count": 30},
                {"tag": "diamond", "count": 25},
            ],
            "category_leaders": {
                "engagement_rings": {"top_shop": "BestShop",
                                     "total_shops": 2, "avg_shop_price": 900.0,
                                     "total_listings": 20, "top_engagement": 10000},
            },
            "shops_by_category": {"engagement_rings": 2, "gold_necklaces": 1},
            "shops_by_tier": {"premium": 3, "luxury": 2},
            "avg_shop_listings": 10.0,
            "top_materials_used": [
                {"material": "gold", "count": 30, "avg_price": 800.0, "pct": 60.0},
            ],
        }

        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
            fine_jewelry_insights=fj_insights,
        )
        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("Fine Jewelry", content)
        self.assertIn("BestShop", content)
        self.assertIn("14K", content)
        self.assertIn("Diamond", content)

    def test_generate_pdf_fallback(self):
        """PDF generation should gracefully fail if weasyprint unavailable."""
        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
        )
        pdf_path = self.generator.generate_pdf(path)
        # May be None if weasyprint not installed — that's acceptable
        self.assertIsNone(pdf_path)

    def test_report_filename_contains_date(self):
        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
            report_date=date(2024, 6, 15),
        )
        self.assertIn("20240615", path)

    def test_commodity_prices_section(self):
        """Test that commodity prices render properly."""
        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
        )
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("Precious Metal", content)
        self.assertIn("Gold", content)

    def test_headlines_section(self):
        """Test headlines render correctly."""
        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
        )
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("Top 10 Industry Headlines", content)
        self.assertIn("Diamond Market", content)

    def test_etsy_intel_section(self):
        """Test Etsy section renders correctly."""
        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
        )
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("Etsy Intelligence", content)
        self.assertIn("SEO Features", content)

    def test_footer_contains_disclaimer(self):
        path = self.generator.generate_html(
            articles=self.sample_articles,
            headlines=self.sample_headlines,
            etsy_intel=self.sample_etsy_intel,
            commodity_prices=self.sample_commodity_prices,
            session_summary=self.session_summary,
        )
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("Disclaimer", content)


if __name__ == "__main__":
    unittest.main()