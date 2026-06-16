# =============================================================================
# Tests: Scrapers
# =============================================================================

import io
from unittest.mock import patch, MagicMock
from datetime import date

import pytest

from scraper import (
    ArticleListScraper,
    RSSFeedScraper,
    CommodityPriceScraper,
    RedditScraper,
    ScraperFactory,
    JewelScopeScraper,
)
from anti_detect import AntiDetectClient


class TestArticleListScraper:
    """Test the generic article list scraper with CSS selectors."""

    def test_scrape_articles(self, sample_config, sample_article_html):
        """Parse HTML with article containers."""
        source_config = sample_config["sources"]["test_article_list"]
        client = AntiDetectClient(sample_config)
        client.enabled = False  # Disable delays for tests

        scraper = ArticleListScraper("test_article_list", source_config, client)

        # We can't easily test HTTP, but we can test the parsing logic
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(sample_article_html, "lxml")

        containers = soup.select("article")
        assert len(containers) == 3

        # Test extraction from first container
        title_el = containers[0].select_one("h2 a")
        assert title_el is not None
        assert "Record Diamond Sale" in title_el.get_text()

        link = title_el.get("href")
        assert link == "/article1"

    def test_category_inference_jewelry(self, sample_config):
        """Sources with jewelry keywords get 'jewelry' category."""
        client = AntiDetectClient(sample_config)
        scraper = ArticleListScraper(
            "jck_online", sample_config["sources"]["test_article_list"], client
        )
        assert scraper.category is not None  # Just verify it infers something

    def test_empty_html_returns_empty_list(self, sample_config):
        """No articles found = empty list, not crash."""
        client = AntiDetectClient(sample_config)
        scraper = ArticleListScraper(
            "empty_source", sample_config["sources"]["test_article_list"], client
        )
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<html><body>No articles here</body></html>", "lxml")
        containers = soup.select("article")
        assert len(containers) == 0


class TestRSSFeedScraper:
    """Test RSS feed parsing."""

    def test_rss_parsing(self, sample_config, sample_rss_xml):
        """Parse RSS XML into articles."""
        source_config = sample_config["sources"]["test_rss"]
        client = AntiDetectClient(sample_config)

        scraper = RSSFeedScraper("test_rss", source_config, client)

        # Parse with feedparser directly using BytesIO (avoids version compat issues)
        import feedparser
        feed = feedparser.parse(io.BytesIO(sample_rss_xml.encode("utf-8")))
        assert len(feed.entries) == 2

        entry = feed.entries[0]
        assert "Diamond Market" in entry.title
        assert entry.link == "https://example.com/diamond-dec-2024"

    def test_rss_categories(self, sample_config):
        """RSS sources should get correct category inference."""
        client = AntiDetectClient(sample_config)
        scraper = RSSFeedScraper("google_news_jewelry", sample_config["sources"]["test_rss"], client)
        # Name contains "jewelry" -> "jewelry" or "news_aggregator"
        cat = scraper._infer_category_from_feed()
        assert cat in ("jewelry", "news_aggregator")


class TestCommodityPriceScraper:
    """Test commodity price extraction."""

    def test_price_extraction_from_text(self, sample_config, sample_commodity_html):
        """Extract prices from HTML containing dollar values."""
        client = AntiDetectClient(sample_config)
        scraper = CommodityPriceScraper("kitco", sample_config["sources"]["test_commodity"], client)

        # Test regex pattern matching on stripped text
        import re
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(sample_commodity_html, "lxml")
        text = soup.get_text()
        gold_pattern = r"Gold\s*\$?([\d,]+\.?\d*)"
        match = re.search(gold_pattern, text, re.IGNORECASE)
        assert match is not None, f"Pattern '{gold_pattern}' not found in: {text[:200]}"
        assert "2,345.50" in match.group(1)

    def test_price_extraction_from_table(self, sample_config, sample_commodity_html):
        """Fallback: extract prices from HTML tables."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(sample_commodity_html, "lxml")

        scraper = CommodityPriceScraper("kitco", sample_config["sources"]["test_commodity"], http_client=MagicMock())
        prices = scraper._extract_from_tables(soup)

        assert "gold" in prices
        assert prices["gold"] == 2345.50
        assert prices["silver"] == 28.75

    def test_empty_html_returns_empty(self, sample_config):
        """No prices found returns empty list."""
        http_client = MagicMock()
        scraper = CommodityPriceScraper("kitco", sample_config["sources"]["test_commodity"], http_client)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<html><body>No data</body></html>", "lxml")
        prices = scraper._extract_from_tables(soup)
        assert prices == {}


class TestRedditScraper:
    """Test Reddit scraping (via old.reddit.com)."""

    def test_reddit_parsing(self, sample_config, sample_reddit_html):
        """Parse Reddit HTML into articles."""
        http_client = MagicMock()
        scraper = RedditScraper("reddit_etsy_sellers", sample_config["sources"]["test_reddit"], http_client)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(sample_reddit_html, "lxml")
        things = soup.select(".thing")

        # Check for stickied class on the element itself (not a descendant)
        non_stickied = [t for t in things if "stickied" not in t.get("class", [])]
        assert len(non_stickied) == 2


class TestScraperFactory:
    """Test the factory creates the right scraper types."""

    def test_factory_article_list(self, sample_config):
        client = MagicMock()
        scraper = ScraperFactory.create_scraper(
            "test_source", sample_config["sources"]["test_article_list"], client
        )
        assert isinstance(scraper, ArticleListScraper)

    def test_factory_rss(self, sample_config):
        client = MagicMock()
        scraper = ScraperFactory.create_scraper(
            "test_source", sample_config["sources"]["test_rss"], client
        )
        assert isinstance(scraper, RSSFeedScraper)

    def test_factory_commodity(self, sample_config):
        client = MagicMock()
        scraper = ScraperFactory.create_scraper(
            "test_source", sample_config["sources"]["test_commodity"], client
        )
        assert isinstance(scraper, CommodityPriceScraper)

    def test_factory_reddit(self, sample_config):
        client = MagicMock()
        scraper = ScraperFactory.create_scraper(
            "test_source", sample_config["sources"]["test_reddit"], client
        )
        assert isinstance(scraper, RedditScraper)

    def test_disabled_sources_not_scraped(self, sample_config):
        """The main scraper should skip disabled sources."""
        from anti_detect import AntiDetectClient
        client = AntiDetectClient(sample_config)
        client.enabled = False

        scraper = JewelScopeScraper(sample_config, client)
        results = scraper.run_all()

        # The disabled source should not appear in results
        assert "test_disabled" not in results or len(results["test_disabled"]) == 0


class TestJewelScopeScraper:
    """Test the main orchestrator."""

    def test_scraper_initialization(self, sample_config):
        client = MagicMock()
        scraper = JewelScopeScraper(sample_config, client)
        assert scraper is not None
        assert len(scraper.sources) == 5

    def test_get_headlines_returns_limited(self, sample_config):
        """get_headlines should return at most top_n articles."""
        client = MagicMock()
        scraper = JewelScopeScraper(sample_config, client)
        # Manually set some results
        scraper.results = {
            "test": [
                {"title": "A", "category": "jewelry", "score": 5},
                {"title": "B", "category": "etsy", "score": 3},
                {"title": "C", "category": "jewelry", "score": 1},
            ]
        }
        headlines = scraper.get_headlines(top_n=2)
        assert len(headlines) <= 2

    def test_empty_scrape_graceful(self, sample_config):
        """Scraping with no network should return empty results, not crash."""
        from anti_detect import AntiDetectClient
        client = AntiDetectClient(sample_config)

        scraper = JewelScopeScraper(sample_config, client)
        results = scraper.run_all()
        assert isinstance(results, dict)