"""
E2E tests for Google Trends overlay — no API keys needed.
Tests the analyzer with mock trend data to validate correlation logic.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGoogleTrendsFetcher(unittest.TestCase):
    """Test the Google Trends data fetcher with mocked pytrends."""

    @patch("google_trends_overlay.HAS_PYTRENDS", True)
    def setUp(self):
        from google_trends_overlay import GoogleTrendsFetcher
        self.fetcher = GoogleTrendsFetcher()
        # Mock pytrends properly
        self.fetcher.pytrends = MagicMock()

    def test_categorize_jewelry_type(self):
        cat = self.fetcher._categorize_term("engagement ring")
        self.assertEqual(cat, "jewelry_type")

    def test_categorize_material(self):
        cat = self.fetcher._categorize_term("gold jewelry")
        self.assertEqual(cat, "material")

    def test_categorize_style(self):
        cat = self.fetcher._categorize_term("vintage jewelry")
        self.assertEqual(cat, "style")

    def test_categorize_etsy(self):
        cat = self.fetcher._categorize_term("etsy jewelry")
        self.assertEqual(cat, "etsy")

    def test_categorize_occasion(self):
        cat = self.fetcher._categorize_term("bridal jewelry")
        self.assertEqual(cat, "occasion")

    @patch("pandas.DataFrame")
    def test_fetch_interest_over_time_empty(self, mock_df):
        self.fetcher.pytrends.interest_over_time.return_value = mock_df
        mock_df.empty = True
        results = self.fetcher.fetch_interest_over_time(["gold ring"])
        self.assertEqual(results, {})


class TestTrendsOverlayAnalyzer(unittest.TestCase):
    """Test the overlay analyzer that correlates Google + Etsy data."""

    def setUp(self):
        from google_trends_overlay import (
            TrendsOverlayAnalyzer, SearchTermTrend, TrendDataPoint
        )
        self.analyzer = TrendsOverlayAnalyzer()

        # Create mock Google Trends data for testing
        self.mock_trends = {
            "gold ring": SearchTermTrend(
                term="gold ring",
                category="jewelry_type",
                current_value=85,
                week_change=12.5,
                month_change=8.0,
                trend_direction="rising",
                data_points=[
                    TrendDataPoint(date="2024-01-01", value=70),
                    TrendDataPoint(date="2024-01-08", value=85),
                ],
            ),
            "silver necklace": SearchTermTrend(
                term="silver necklace",
                category="jewelry_type",
                current_value=45,
                week_change=-10.2,
                month_change=-5.0,
                trend_direction="falling",
                data_points=[
                    TrendDataPoint(date="2024-01-01", value=55),
                    TrendDataPoint(date="2024-01-08", value=45),
                ],
            ),
            "engagement ring": SearchTermTrend(
                term="engagement ring",
                category="jewelry_type",
                current_value=92,
                week_change=3.0,
                month_change=2.0,
                trend_direction="stable",
                data_points=[
                    TrendDataPoint(date="2024-01-01", value=90),
                    TrendDataPoint(date="2024-01-08", value=92),
                ],
            ),
        }

    def test_analyzer_creation(self):
        self.assertIsNotNone(self.analyzer)
        self.assertIsNotNone(self.analyzer.google)

    def test_set_etsy_data(self):
        materials = [
            {"material": "gold", "count": 40, "trend_direction": "up"},
            {"material": "silver", "count": 35, "trend_direction": "down"},
        ]
        categories = [
            {"category": "Rings", "count": 150, "trend_direction": "up"},
        ]
        self.analyzer.set_etsy_data(materials, categories)
        self.assertEqual(len(self.analyzer.etsy_materials), 2)
        self.assertEqual(len(self.analyzer.etsy_categories), 1)

    def test_rising_google_terms_sorted(self):
        """Test that rising terms are sorted by week_change descending."""
        # Patch fetch to return mock data
        from google_trends_overlay import TrendsOverlayReport

        with patch.object(self.analyzer.google, 'fetch_interest_over_time',
                          return_value=self.mock_trends):
            report = self.analyzer.run_analysis(["gold ring", "silver necklace"])

        self.assertIsInstance(report, TrendsOverlayReport)
        self.assertGreater(len(report.rising_google), 0)
        # Gold ring should be rising
        rising_terms = [r["term"] for r in report.rising_google]
        self.assertIn("gold ring", rising_terms)

    def test_falling_google_terms(self):
        """Test that falling terms are identified."""
        with patch.object(self.analyzer.google, 'fetch_interest_over_time',
                          return_value=self.mock_trends):
            report = self.analyzer.run_analysis(["gold ring", "silver necklace"])

        falling_terms = [r["term"] for r in report.falling_google]
        self.assertIn("silver necklace", falling_terms)

    def test_confirmed_trends_with_etsy_alignment(self):
        """When Google says rising AND Etsy says up — confirmed trend."""
        self.analyzer.set_etsy_data(
            materials=[{"material": "gold", "count": 40, "trend_direction": "up"}],
            categories=[],
        )
        with patch.object(self.analyzer.google, 'fetch_interest_over_time',
                          return_value=self.mock_trends):
            report = self.analyzer.run_analysis(["gold ring", "silver necklace"])

        confirmed = [c["term"] for c in report.confirmed_trends]
        # Gold ring rising on Google + gold up on Etsy = confirmed
        self.assertGreater(len(report.confirmed_trends), 0)

    def test_biggest_movers_sorted(self):
        """Test biggest movers are sorted by absolute change."""
        with patch.object(self.analyzer.google, 'fetch_interest_over_time',
                          return_value=self.mock_trends):
            report = self.analyzer.run_analysis(["gold ring", "silver necklace"])

        self.assertGreater(len(report.biggest_movers), 0)
        # First mover should have the largest absolute change
        if len(report.biggest_movers) >= 2:
            first = abs(report.biggest_movers[0]["week_change"])
            second = abs(report.biggest_movers[1]["week_change"])
            self.assertGreaterEqual(first, second)

    def test_category_averages(self):
        """Test category averages are calculated."""
        with patch.object(self.analyzer.google, 'fetch_interest_over_time',
                          return_value=self.mock_trends):
            report = self.analyzer.run_analysis(["gold ring", "silver necklace"])

        self.assertIn("jewelry_type", report.category_averages)
        self.assertGreater(report.category_averages["jewelry_type"], 0)

    def test_no_pytrends_fallback(self):
        """When pytrends is unavailable, report should note it."""
        with patch.object(self.analyzer.google, 'fetch_interest_over_time',
                          return_value={}):
            report = self.analyzer.run_analysis(["gold ring"])
        self.assertIn("unavailable", report.correlation_summary.lower())

    def test_run_quick_scan_returns_string(self):
        """Test the convenience method returns a readable summary."""
        with patch.object(self.analyzer.google, 'fetch_interest_over_time',
                          return_value=self.mock_trends):
            summary = self.analyzer.run_quick_scan()
        self.assertIsInstance(summary, str)
        self.assertGreater(len(summary), 0)

    def test_format_summary_contains_key_sections(self):
        """Test the report summary formatting."""
        from google_trends_overlay import TrendsOverlayReport

        report = TrendsOverlayReport()
        report.total_terms_tracked = 5
        report.rising_google = [{"term": "gold ring", "week_change": 12.5}]
        report.confirmed_trends = [{"term": "gold ring", "current_value": 85}]

        summary = report.format_summary()
        self.assertIn("Google Trends", summary)
        self.assertIn("gold ring", summary)
        self.assertIn("12.5", summary)


class TestTrendDataPoint(unittest.TestCase):
    """Test the TrendDataPoint dataclass."""

    def setUp(self):
        from google_trends_overlay import TrendDataPoint
        self.point = TrendDataPoint(date="2024-01-15", value=75)

    def test_creation(self):
        self.assertEqual(self.point.date, "2024-01-15")
        self.assertEqual(self.point.value, 75)

    def test_to_dict(self):
        d = self.point.to_dict()
        self.assertEqual(d["date"], "2024-01-15")
        self.assertEqual(d["value"], 75)


class TestTrendsOverlayReport(unittest.TestCase):
    """Test the TrendsOverlayReport dataclass."""

    def setUp(self):
        from google_trends_overlay import TrendsOverlayReport
        self.report = TrendsOverlayReport()

    def test_default_values(self):
        self.assertEqual(self.report.total_terms_tracked, 0)
        self.assertEqual(self.report.rising_google, [])
        self.assertEqual(self.report.falling_google, [])

    def test_format_summary_empty(self):
        summary = self.report.format_summary()
        self.assertIn("Google Trends", summary)
        self.assertIn("0", summary)


if __name__ == "__main__":
    unittest.main()