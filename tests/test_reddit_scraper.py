import unittest
from unittest.mock import MagicMock, patch
import asyncio
from utils.reddit_scraper import RedditScraper
import os

class TestRedditScraper(unittest.TestCase):
    def setUp(self):
        self.source_config = {
            "subreddit": "testsub",
            "query": "testquery"
        }
        # Set dummy environment variables for setup
        os.environ['REDDIT_CLIENT_ID'] = 'id'
        os.environ['REDDIT_CLIENT_SECRET'] = 'secret'
        os.environ['REDDIT_USER_AGENT'] = 'ua'
        
        with patch('praw.Reddit') as mock_reddit:
            self.scraper = RedditScraper("TestReddit", self.source_config, MagicMock())
            self.mock_reddit = mock_reddit

    def test_scrape_success(self):
        # Mock subreddit and search results
        mock_subreddit = MagicMock()
        self.scraper.reddit.subreddit.return_value = mock_subreddit
        
        mock_post = MagicMock()
        mock_post.title = "Test Post"
        mock_post.url = "http://test.url"
        mock_post.created_utc = 1781481600 # June 15 2026
        mock_post.selftext = "Test body"
        
        mock_subreddit.search.return_value = [mock_post]
        
        # Run
        results = asyncio.run(self.scraper.scrape())
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "Test Post")
        self.assertEqual(results[0]['url'], "http://test.url")
        self.assertEqual(results[0]['published_date'], "2026-06-15")

if __name__ == '__main__':
    unittest.main()
