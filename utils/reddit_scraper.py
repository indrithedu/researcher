import os
import logging
import praw
import prawcore
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class RedditScraper:
    def __init__(self, source_name: str, source_config: dict, http_client: Any):
        self.name = source_name
        self.source_config = source_config
        self.url = source_config.get("url", "")
        # PRAW client setup
        self.reddit = praw.Reddit(
            client_id=os.environ.get("REDDIT_CLIENT_ID"),
            client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
            user_agent=os.environ.get("REDDIT_USER_AGENT")
        )

    async def scrape(self) -> List[Dict[str, Any]]:
        articles = []
        subreddit_name = self.source_config.get("subreddit", "all")
        query = self.source_config.get("query", "")
        
        try:
            # Run sync PRAW in thread to avoid blocking asyncio loop
            def _do_scrape():
                subreddit = self.reddit.subreddit(subreddit_name)
                # PRAW handles rate limits automatically
                results = subreddit.search(query, limit=20)
                posts = []
                for post in results:
                    posts.append({
                        "source_name": self.name,
                        "source_url": f"https://www.reddit.com/r/{subreddit_name}",
                        "title": post.title,
                        "url": post.url,
                        "published_date": datetime.fromtimestamp(post.created_utc, timezone.utc).strftime("%Y-%m-%d"),
                        "summary": post.selftext[:500] if post.selftext else "",
                        "category": "etsy", 
                        "is_headline": False,
                    })
                return posts
            
            loop = asyncio.get_event_loop()
            articles = await loop.run_in_executor(None, _do_scrape)
        
        except prawcore.exceptions.RequestException as e:
            logger.error(f"Reddit API error: {e}")
        except Exception as e:
            logger.error(f"Reddit scrape failed: {e}")
        
        return articles
