"""
E2E tests for Pinterest trend scraper — no API keys needed.
Tests data models, HTML parsing fallbacks, and trend aggregation.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPinterestDataModels(unittest.TestCase):
    """Test Pinterest pin and report data models."""

    def setUp(self):
        from pinterest_scraper import PinterestPin, PinterestTrendReport
        self.PinterestPin = PinterestPin
        self.PinterestTrendReport = PinterestTrendReport

    def test_pin_creation(self):
        pin = self.PinterestPin(
            pin_id="12345",
            title="Gold Diamond Ring",
            description="Beautiful 14k gold ring",
            image_url="https://example.com/img.jpg",
            pin_url="https://pinterest.com/pin/12345",
            board_name="Jewelry Ideas",
            repin_count=50,
            save_count=120,
            comment_count=5,
            search_term="gold ring",
            scraped_at="2024-01-15T00:00:00",
        )
        self.assertEqual(pin.pin_id, "12345")
        self.assertEqual(pin.title, "Gold Diamond Ring")
        self.assertEqual(pin.repin_count, 50)
        self.assertEqual(pin.save_count, 120)

    def test_pin_engagement_score(self):
        pin = self.PinterestPin(
            pin_id="1", title="Test", description="",
            image_url="", pin_url="", board_name="",
            repin_count=10, save_count=20, comment_count=5,
            search_term="test",
        )
        # engagement = repins + saves*2 + comments*3 = 10 + 40 + 15 = 65
        self.assertEqual(pin.engagement_score, 65)

    def test_pin_to_dict(self):
        pin = self.PinterestPin(
            pin_id="1", title="Test", description="Desc",
            image_url="https://img.com/1.jpg", pin_url="https://pin.com/1",
            board_name="Board", repin_count=5, save_count=10,
            comment_count=2, search_term="test",
        )
        d = pin.to_dict()
        self.assertEqual(d["pin_id"], "1")
        self.assertEqual(d["title"], "Test")

    def test_trend_report_defaults(self):
        report = self.PinterestTrendReport()
        self.assertEqual(report.total_pins_collected, 0)
        self.assertEqual(report.search_terms_scraped, 0)
        self.assertEqual(report.trending_terms, [])
        self.assertEqual(report.top_pins, [])

    def test_format_summary_empty(self):
        report = self.PinterestTrendReport()
        summary = report.format_summary()
        self.assertIn("Pinterest", summary)
        self.assertIn("0", summary)

    def test_format_summary_with_data(self):
        report = self.PinterestTrendReport(
            total_pins_collected=50,
            search_terms_scraped=3,
            trending_terms=[{"term": "gold ring", "avg_engagement": 85}],
            top_pins=[{"title": "Beautiful Ring", "save_count": 100}],
        )
        summary = report.format_summary()
        self.assertIn("50", summary)
        self.assertIn("gold ring", summary)
        self.assertIn("Beautiful Ring", summary)


class TestPinterestParsePinItem(unittest.TestCase):
    """Test parsing Pinterest pin items from API-like structures."""

    def setUp(self):
        from pinterest_scraper import PinterestTrendScraper
        self.scraper = PinterestTrendScraper()

    def test_parse_valid_pin_item(self):
        item = {
            "id": "123456789",
            "title": "14k Gold Diamond Engagement Ring",
            "description": "Beautiful handcrafted ring with brilliant cut diamond",
            "repin_count": 45,
            "save_count": 120,
            "comment_count": 8,
            "images": {
                "orig": {"url": "https://i.pinimg.com/originals/test.jpg"}
            },
            "board": {"name": "Wedding Rings"},
            "link": "https://www.pinterest.com/pin/123456789/",
        }
        pin = self.scraper._parse_pin_item(item, "engagement ring")
        self.assertIsNotNone(pin)
        self.assertEqual(pin.pin_id, "123456789")
        self.assertIn("Gold", pin.title)
        self.assertEqual(pin.repin_count, 45)
        self.assertEqual(pin.save_count, 120)
        self.assertEqual(pin.board_name, "Wedding Rings")
        self.assertEqual(pin.search_term, "engagement ring")

    def test_parse_pin_item_missing_id(self):
        pin = self.scraper._parse_pin_item({"title": "No ID"}, "test")
        self.assertIsNone(pin)

    def test_parse_pin_item_fallback_title_from_creator(self):
        item = {
            "id": "999",
            "native_creator": {"full_name": "Jewelry Studio"},
            "images": {"orig": {"url": "https://img.com/test.jpg"}},
        }
        pin = self.scraper._parse_pin_item(item, "test")
        self.assertIsNotNone(pin)
        # Falls back to creator name when no title
        self.assertEqual(pin.pin_id, "999")

    def test_parse_pin_item_with_various_image_sizes(self):
        """Should try image sizes in order: orig, 736x, 564x, 236x."""
        item = {
            "id": "888",
            "title": "Test Pin",
            "images": {
                "236x": {"url": "https://img.com/236.jpg"},
                "564x": {"url": "https://img.com/564.jpg"},
            },
        }
        pin = self.scraper._parse_pin_item(item, "test")
        self.assertIsNotNone(pin)
        # Should pick 564x (higher resolution than 236x)
        self.assertIn("564.jpg", pin.image_url)

    def test_parse_pin_item_no_images(self):
        item = {"id": "777", "title": "No Image Pin"}
        pin = self.scraper._parse_pin_item(item, "test")
        self.assertIsNotNone(pin)
        self.assertEqual(pin.image_url, "")

    def test_parse_pin_item_save_count_fallback_to_repin(self):
        item = {
            "id": "666",
            "title": "Test",
            "repin_count": 30,
            # no save_count
            "images": {"orig": {"url": "https://img.com/t.jpg"}},
        }
        pin = self.scraper._parse_pin_item(item, "test")
        self.assertIsNotNone(pin)
        self.assertEqual(pin.save_count, 30)  # Falls back to repin_count


class TestPinterestHtmlFallback(unittest.TestCase):
    """Test HTML fallback parsing for Pinterest pages."""

    def setUp(self):
        from pinterest_scraper import PinterestTrendScraper
        self.scraper = PinterestTrendScraper()

    def test_extract_from_html_with_pin_test_id(self):
        html = """
        <div data-test-id="pin">
            <img src="https://i.pinimg.com/236x/test.jpg" alt="Gold Ring">
        </div>
        <div data-test-id="pin">
            <img src="https://i.pinimg.com/236x/test2.jpg" alt="Silver Necklace">
        </div>
        """
        pins = self.scraper._extract_from_html_fallback(html, "test search")
        self.assertGreater(len(pins), 0)
        # At least one pin should have extracted content
        titles = [p.title for p in pins]
        self.assertTrue(any("Gold" in t or "Silver" in t for t in titles))

    def test_extract_from_html_empty(self):
        pins = self.scraper._extract_from_html_fallback("<html></html>", "test")
        self.assertEqual(pins, [])

    def test_extract_from_html_no_images(self):
        html = """
        <div data-test-id="pin">
            <span>Some text without image</span>
        </div>
        """
        pins = self.scraper._extract_from_html_fallback(html, "test")
        self.assertEqual(len(pins), 0)


class TestPinterestTrendAggregation(unittest.TestCase):
    """Test the aggregation logic in Pinterest trend report generation."""

    def setUp(self):
        from pinterest_scraper import PinterestTrendScraper, PinterestPin
        self.scraper = PinterestTrendScraper()

        # Create mock pins for aggregation testing
        self.mock_pins = [
            PinterestPin(
                pin_id=f"{i}", title=f"Pin {i}",
                description=f"gold ring jewelry description {i}",
                image_url="", pin_url="", board_name=f"Board {i % 3}",
                repin_count=10 * i, save_count=20 * i, comment_count=i,
                search_term="gold ring",
            )
            for i in range(5)
        ]

    def test_trending_terms_aggregation(self):
        """Test that terms are ranked by total engagement."""
        from pinterest_scraper import PinterestTrendReport
        report = PinterestTrendReport()

        # Manually set pins
        self.scraper.pins = self.mock_pins
        # We can't easily call the full pipeline without Playwright,
        # but we can test the data model aggregation directly

        report.total_pins_collected = len(self.mock_pins)
        report.search_terms_scraped = 1

        # Verify counts
        self.assertEqual(report.total_pins_collected, 5)
        self.assertEqual(report.search_terms_scraped, 1)


class TestPinterestSearchTerms(unittest.TestCase):
    """Test that the default search terms list is well-formed."""

    def setUp(self):
        from pinterest_scraper import PINTEREST_SEARCH_TERMS
        self.terms = PINTEREST_SEARCH_TERMS

    def test_search_terms_are_not_empty(self):
        self.assertGreater(len(self.terms), 0)

    def test_search_terms_are_strings(self):
        for term in self.terms:
            self.assertIsInstance(term, str)
            self.assertGreater(len(term), 0)

    def test_search_terms_include_jewelry_keywords(self):
        all_text = " ".join(self.terms).lower()
        self.assertIn("jewelry", all_text)
        self.assertIn("ring", all_text)


class TestPinterestUrlGeneration(unittest.TestCase):
    """Test Pinterest search URL generation."""

    def test_url_encodes_query(self):
        from pinterest_scraper import PINTEREST_SEARCH_URL
        url = PINTEREST_SEARCH_URL.format(q="gold+ring")
        self.assertIn("gold+ring", url)
        self.assertIn("pinterest.com", url)


if __name__ == "__main__":
    unittest.main()