
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from scraper import ArticleListScraper, RSSFeedScraper, CommodityPriceScraper, RedditScraper
from anti_detect import AntiDetectClient

class TestScrapers(unittest.TestCase):

    def setUp(self):
        self.mock_client = MagicMock(spec=AntiDetectClient)
        self.mock_client.async_get = AsyncMock()
        self.source_config = {
            "url": "https://example.com/news",
            "selectors": {
                "article_container": "article",
                "title": "h2 a",
                "link": "h2 a",
                "date": "time",
                "summary": "p"
            }
        }

    def test_article_list_scraper_success(self):
        html = """
        <html>
            <body>
                <article>
                    <h2><a href="/post1">Title 1</a></h2>
                    <time datetime="2024-01-01">Jan 1, 2024</time>
                    <p>Summary 1</p>
                </article>
                <article>
                    <h2><a href="/post2">Title 2</a></h2>
                    <time datetime="2024-01-02">Jan 2, 2024</time>
                    <p>Summary 2</p>
                </article>
            </body>
        </html>
        """
        self.mock_client.async_get.return_value = (html, 200)
        scraper = ArticleListScraper("Test Source", self.source_config, self.mock_client)
        articles = asyncio.run(scraper.scrape())

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["title"], "Title 1")
        self.assertEqual(articles[0]["url"], "https://example.com/post1")
        self.assertEqual(articles[0]["published_date"], "2024-01-01")
        self.assertEqual(articles[0]["summary"], "Summary 1")
        self.assertEqual(articles[1]["title"], "Title 2")

    def test_article_list_scraper_missing_fields(self):
        html = """
        <html>
            <body>
                <article>
                    <h2><a href="/post1">Title 1</a></h2>
                </article>
            </body>
        </html>
        """
        self.mock_client.async_get.return_value = (html, 200)
        scraper = ArticleListScraper("Test Source", self.source_config, self.mock_client)
        articles = asyncio.run(scraper.scrape())

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Title 1")
        self.assertEqual(articles[0]["published_date"], "")
        self.assertEqual(articles[0]["summary"], "")

    def test_rss_feed_scraper(self):
        rss_content = """<?xml version="1.0" encoding="UTF-8" ?>
        <rss version="2.0">
        <channel>
            <title>Test RSS</title>
            <item>
                <title>RSS Title 1</title>
                <link>https://example.com/rss1</link>
                <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
                <description>RSS Summary 1</description>
            </item>
        </channel>
        </rss>
        """
        # RSSFeedScraper uses feedparser which can take URL or string.
        # But in scraper.py, it uses self.client.get(self.url) is NOT called for RSS!
        # Wait, let me check RSSFeedScraper.scrape again.
        
        # Checking scraper.py lines 163-165:
        # def scrape(self) -> List[Dict[str, Any]]:
        #     articles = []
        #     try:
        #         # Use feedparser for RSS/Atom feeds
        #         feed = feedparser.parse(self.url)
        
        # Ah! It calls feedparser.parse(self.url) directly, bypassing the client!
        # This is a bug in the original code if they wanted to use anti-detection for RSS too.
        # But for testing, I need to mock feedparser.parse.

        with patch("feedparser.parse") as mock_parse:
            mock_feed = MagicMock()
            mock_feed.entries = [
                {
                    "title": "RSS Title 1",
                    "link": "https://example.com/rss1",
                    "published": "Mon, 01 Jan 2024 00:00:00 GMT",
                    "summary": "RSS Summary 1"
                }
            ]
            mock_parse.return_value = mock_feed
            self.mock_client.async_get.return_value = ("<rss></rss>", 200)

            scraper = RSSFeedScraper("RSS Source", {"url": "https://example.com/rss"}, self.mock_client)
            articles = asyncio.run(scraper.scrape())

            self.assertEqual(len(articles), 1)
            self.assertEqual(articles[0]["title"], "RSS Title 1")
            self.assertEqual(articles[0]["published_date"], "2024-01-01")

    def test_commodity_price_scraper_regex(self):
        html = "Current gold price is Gold $2,050.50 and Silver is $23.45"
        self.mock_client.async_get.return_value = (html, 200)
        
        scraper = CommodityPriceScraper("Kitco", {"url": "https://kitco.com"}, self.mock_client)
        articles = asyncio.run(scraper.scrape())

        # It creates one article per metal
        # Note: scraper.py:246: "title": f"{metal.title()} Price: ${price:,.2f}/oz"
        
        gold_article = next((a for a in articles if "Gold" in a["title"]), None)
        silver_article = next((a for a in articles if "Silver" in a["title"]), None)

        self.assertIsNotNone(gold_article)
        self.assertIn("$2,050.50", gold_article["title"])
        self.assertIsNotNone(silver_article)
        self.assertIn("$23.45", silver_article["title"])

    def test_commodity_price_scraper_table(self):
        html = """
        <table>
            <tr><td>Gold</td><td>2060.00</td></tr>
            <tr><td>Silver</td><td>24.00</td></tr>
        </table>
        """
        self.mock_client.async_get.return_value = (html, 200)
        
        scraper = CommodityPriceScraper("Kitco", {"url": "https://kitco.com"}, self.mock_client)
        articles = asyncio.run(scraper.scrape())

        gold_article = next((a for a in articles if "Gold" in a["title"]), None)
        self.assertIsNotNone(gold_article)
        self.assertIn("$2,060.00", gold_article["title"])

    def test_reddit_scraper(self):
        html = """
        <div class="thing">
            <a class="title">Reddit Post 1</a>
            <time datetime="2024-01-01T00:00:00Z">2024-01-01</time>
            <div class="entry"><div class="usertext-body"><p>Reddit Summary 1</p></div></div>
        </div>
        """
        self.mock_client.async_get.return_value = (html, 200)
        
        scraper = RedditScraper("Reddit", {"url": "https://old.reddit.com/r/test"}, self.mock_client)
        articles = asyncio.run(scraper.scrape())

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Reddit Post 1")
        self.assertEqual(articles[0]["published_date"], "2024-01-01")

if __name__ == "__main__":
    unittest.main()
