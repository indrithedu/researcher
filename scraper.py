# =============================================================================
# JewelScope Research — Scraper Module
# =============================================================================
# Handles scraping of every configured news source, commodity feed, and
# social channel. Each site has its own scraping strategy depending on
# whether it uses JavaScript rendering, has anti-bot protection, or
# provides plain HTML.
#
# All HTTP calls go through AntiDetectClient which handles proxies, UA
# rotation, TLS fingerprinting, and request throttling.
# =============================================================================

import re
import json
import random
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup
import feedparser

from anti_detect import AntiDetectClient, StealthBrowser, USER_AGENT_POOL

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Raised when a source cannot be scraped after all retries."""
    pass


# =============================================================================
# Base Scraper
# =============================================================================

class BaseSourceScraper:
    """Base class for all source scrapers."""

    def __init__(self, source_name: str, source_config: dict, http_client: AntiDetectClient):
        self.name = source_name
        self.config = source_config
        self.client = http_client
        self.url = source_config.get("url", "")
        self.enabled = source_config.get("enabled", True)
        self.selectors = source_config.get("selectors", {})

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape the source and return a list of articles.
        Each article dict has: source_name, source_url, title, url,
                              published_date, summary, category, is_headline
        """
        raise NotImplementedError

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        if not text:
            return ""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove common boilerplate
        text = re.sub(r'(^|\s)(Read More|Continue Reading|Related:|Share this|Click here)(\s|$)', '', text, flags=re.IGNORECASE)
        return text.strip()[:500]  # Limit summary length

    def _parse_date(self, date_str: str) -> str:
        """Try to parse a date string into a standardized format."""
        if not date_str:
            return ""
        date_str = date_str.strip()
        # Try common date formats
        formats = [
            "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y",
            "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%A, %B %d, %Y",
            "%B %d", "%b %d",  # Without year — will need year inference
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If year is not in the format, assume this year
                if "%Y" not in fmt:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
        # Return original if can't parse
        return date_str


# =============================================================================
# Article List Scraper (generic HTML scraping with CSS selectors)
# =============================================================================

class ArticleListScraper(BaseSourceScraper):
    """
    Scrapes sites that present a list of article links on a page.
    Uses CSS selectors from the config to extract article containers,
    titles, links, dates, and summaries.
    """

    def __init__(self, source_name: str, source_config: dict, http_client: AntiDetectClient):
        super().__init__(source_name, source_config, http_client)
        # Set default category based on source name patterns
        self.category = self._infer_category()

    def _infer_category(self) -> str:
        """Infer article category from source name."""
        name_lower = self.name.lower()
        if any(term in name_lower for term in ["etsy", "ecommercebytes", "marketplacepulse", "reddit"]):
            return "etsy"
        if any(term in name_lower for term in ["kitco", "commodity", "price", "gold", "silver"]):
            return "commodity"
        if any(term in name_lower for term in ["jck", "jeweler", "jewelry", "rapaport", "idex", "loupe"]):
            return "jewelry"
        if any(term in name_lower for term in ["fashion", "vogue", "luxury"]):
            return "fashion_luxury"
        if any(term in name_lower for term in ["google news"]):
            return "news_aggregator"
        return "general"

    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape article listings using CSS selectors."""
        articles = []
        try:
            html, status = self.client.get(self.url)
            if not html or status != 200:
                logger.warning(f"[{self.name}] Got status {status}, no content")
                return articles

            soup = BeautifulSoup(html, "lxml")

            # Find article containers
            container_sel = self.selectors.get("article_container", "article")
            containers = soup.select(container_sel) if container_sel else [soup]

            for container in containers[:20]:  # Max 20 articles per source
                try:
                    # Extract title
                    title_sel = self.selectors.get("title", "h2 a, h3 a")
                    title_el = container.select_one(title_sel) if title_sel else None
                    title = self._clean_text(title_el.get_text()) if title_el else ""

                    if not title:
                        continue

                    # Extract link
                    link_sel = self.selectors.get("link", "h2 a, h3 a")
                    link_el = container.select_one(link_sel) if link_sel else title_el
                    href = ""
                    if link_el and link_el.get("href"):
                        href = urljoin(self.url, link_el["href"])

                    # Extract date
                    date_sel = self.selectors.get("date", "time, .date")
                    date_el = container.select_one(date_sel) if date_sel else None
                    date_text = ""
                    if date_el:
                        # Try datetime attribute first, then text content
                        date_text = date_el.get("datetime", "") or date_el.get_text()
                    parsed_date = self._parse_date(date_text)

                    # Extract summary
                    summary_sel = self.selectors.get("summary", "p, .excerpt, .summary")
                    summary_el = container.select_one(summary_sel) if summary_sel else None
                    summary = self._clean_text(summary_el.get_text()) if summary_el else ""

                    article = {
                        "source_name": self.name,
                        "source_url": self.url,
                        "title": title,
                        "url": href,
                        "published_date": parsed_date,
                        "summary": summary,
                        "category": self.category,
                        "is_headline": False,  # Will be set later by ranking
                    }
                    articles.append(article)

                except Exception as e:
                    logger.debug(f"[{self.name}] Error parsing article container: {e}")
                    continue

            logger.info(f"[{self.name}] Scraped {len(articles)} articles")

        except Exception as e:
            logger.error(f"[{self.name}] Scrape failed: {e}")

        return articles


# =============================================================================
# RSS Feed Scraper
# =============================================================================

class RSSFeedScraper(BaseSourceScraper):
    """
    Scrapes RSS/Atom feeds. Many news sources (including Google News RSS)
    provide clean feeds that avoid the need for HTML parsing entirely.
    """

    def scrape(self) -> List[Dict[str, Any]]:
        """Parse RSS feed and return articles."""
        articles = []
        try:
            # Use feedparser for RSS/Atom feeds
            feed = feedparser.parse(self.url)

            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                published = entry.get("published", "") or entry.get("updated", "")
                summary = entry.get("summary", "") or entry.get("description", "")

                # Clean HTML from summary if present
                if summary:
                    soup = BeautifulSoup(summary, "html.parser")
                    summary = self._clean_text(soup.get_text())

                parsed_date = ""
                try:
                    if published:
                        # feedparser can parse most RSS date formats
                        parsed = datetime(*entry.get("published_parsed", [])[:6]) if entry.get("published_parsed") else None
                        if parsed:
                            parsed_date = parsed.strftime("%Y-%m-%d")
                except Exception:
                    parsed_date = self._parse_date(published)

                article = {
                    "source_name": self.name,
                    "source_url": self.url,
                    "title": title,
                    "url": link,
                    "published_date": parsed_date,
                    "summary": summary,
                    "category": self._infer_category_from_feed(),
                    "is_headline": False,
                }
                articles.append(article)

            logger.info(f"[{self.name}] RSS feed: {len(articles)} entries")

        except Exception as e:
            logger.error(f"[{self.name}] RSS parse failed: {e}")

        return articles

    def _infer_category_from_feed(self) -> str:
        """Infer category from RSS feed URL or title."""
        name_lower = self.name.lower()
        url_lower = self.url.lower()
        if "etsy" in name_lower or "etsy" in url_lower:
            return "etsy"
        if "jewelry" in name_lower or "jewelry" in url_lower or "diamond" in url_lower:
            return "jewelry"
        if "fashion" in name_lower:
            return "fashion_luxury"
        return "news_aggregator"


# =============================================================================
# Commodity Price Scraper (Kitco)
# =============================================================================

class CommodityPriceScraper(BaseSourceScraper):
    """
    Scrapes precious metal prices from Kitco.
    Kitco uses simple HTML tables that are easy to parse.
    """

    PRICE_PATTERNS = {
        "gold": [r"Gold\s*\$?([\d,]+\.?\d*)", r"AU\s*\$?([\d,]+\.?\d*)"],
        "silver": [r"Silver\s*\$?([\d,]+\.?\d*)", r"AG\s*\$?([\d,]+\.?\d*)"],
        "platinum": [r"Platinum\s*\$?([\d,]+\.?\d*)", r"PT\s*\$?([\d,]+\.?\d*)"],
        "palladium": [r"Palladium\s*\$?([\d,]+\.?\d*)", r"PD\s*\$?([\d,]+\.?\d*)"],
    }

    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape Kitco for precious metal prices."""
        articles = []
        try:
            html, status = self.client.get(self.url)
            if not html or status != 200:
                logger.warning(f"[{self.name}] No content (status {status})")
                return articles

            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text()

            # Try to find prices using regex patterns
            prices = {}
            for metal, patterns in self.PRICE_PATTERNS.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        price_str = match.group(1).replace(",", "")
                        try:
                            prices[metal] = float(price_str)
                            break
                        except ValueError:
                            continue

            # If regex failed, try table-based extraction
            if not prices:
                prices = self._extract_from_tables(soup)

            # Create a "price report" article for each metal
            today = date.today().strftime("%Y-%m-%d")
            for metal, price in prices.items():
                articles.append({
                    "source_name": f"{self.name} — {metal.title()}",
                    "source_url": self.url,
                    "title": f"{metal.title()} Price: ${price:,.2f}/oz",
                    "url": self.url,
                    "published_date": today,
                    "summary": f"{metal.title()} spot price at ${price:,.2f} per troy ounce as of {today}.",
                    "category": "commodity",
                    "is_headline": False,
                })

            logger.info(f"[{self.name}] Extracted {len(prices)} commodity prices")

        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")

        return articles

    def _extract_from_tables(self, soup: BeautifulSoup) -> Dict[str, float]:
        """Fallback: extract prices from HTML tables."""
        prices = {}
        table = soup.find("table", class_=re.compile("price|market|rates", re.I))
        if table:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value_text = cells[1].get_text(strip=True)
                    value_text = re.sub(r'[^0-9.]', '', value_text)
                    try:
                        value = float(value_text)
                        for metal_key in ["gold", "silver", "platinum", "palladium"]:
                            if metal_key in label:
                                prices[metal_key] = value
                    except ValueError:
                        continue
        return prices


# =============================================================================
# Reddit Scraper (API-free, uses old.reddit.com)
# =============================================================================

class RedditScraper(BaseSourceScraper):
    """
    Scrapes Reddit subreddits using old.reddit.com which serves clean HTML
    without requiring JavaScript or API keys.
    """

    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape a subreddit listing page."""
        articles = []
        try:
            # Use a more generic UA for Reddit (they block some automated UAs)
            html, status = self.client.get(self.url)
            if not html or status != 200:
                logger.warning(f"[{self.name}] Status {status}")
                return articles

            soup = BeautifulSoup(html, "lxml")

            # Find all post entries
            for thing in soup.select(".thing"):
                try:
                    # Extract title and link
                    title_el = thing.select_one("a.title")
                    if not title_el:
                        continue
                    title = self._clean_text(title_el.get_text())
                    href = urljoin("https://old.reddit.com", title_el.get("href", ""))

                    # Extract date from time tag
                    time_el = thing.select_one("time")
                    date_text = ""
                    if time_el:
                        date_text = time_el.get("datetime", "") or time_el.get_text()
                    parsed_date = self._parse_date(date_text)

                    # Extract summary (self-text preview)
                    summary_el = thing.select_one(".entry .usertext-body p")
                    summary = self._clean_text(summary_el.get_text()) if summary_el else ""

                    # Skip stickied/pinned posts
                    if thing.select_one(".stickied"):
                        continue

                    article = {
                        "source_name": self.name,
                        "source_url": self.url,
                        "title": title,
                        "url": href,
                        "published_date": parsed_date,
                        "summary": summary,
                        "category": "etsy",
                        "is_headline": False,
                    }
                    articles.append(article)

                except Exception as e:
                    logger.debug(f"[{self.name}] Error parsing Reddit entry: {e}")
                    continue

            logger.info(f"[{self.name}] Scraped {len(articles)} Reddit posts")

        except Exception as e:
            logger.error(f"[{self.name}] Reddit scrape failed: {e}")

        return articles


# =============================================================================
# JavaScript Site Scraper (uses StealthBrowser for JS-heavy sites)
# =============================================================================

class JavaScriptSiteScraper(BaseSourceScraper):
    """
    For sites that require JavaScript rendering to display content.
    Uses StealthBrowser (Playwright with stealth patches) to render
    the full page, then extracts articles from the rendered DOM.
    """

    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape a JavaScript-heavy site using a real headless browser."""
        articles = []
        import asyncio

        try:
            browser = StealthBrowser(self.client.config)
            asyncio.run(browser.start())

            try:
                html_content = asyncio.run(browser.navigate(self.url))
            finally:
                asyncio.run(browser.close())

            if not html_content:
                logger.warning(f"[{self.name}] Empty page after JS rendering")
                return articles

            soup = BeautifulSoup(html_content, "lxml")

            # Apply same CSS selector logic as ArticleListScraper
            container_sel = self.selectors.get("article_container", "article")
            containers = soup.select(container_sel) if container_sel else [soup]

            for container in containers[:20]:
                try:
                    title_sel = self.selectors.get("title", "h2 a, h3 a")
                    title_el = container.select_one(title_sel) if title_sel else None
                    title = self._clean_text(title_el.get_text()) if title_el else ""
                    if not title:
                        continue

                    link_sel = self.selectors.get("link", "h2 a, h3 a")
                    link_el = container.select_one(link_sel) if link_sel else title_el
                    href = ""
                    if link_el and link_el.get("href"):
                        href = urljoin(self.url, link_el["href"])

                    date_sel = self.selectors.get("date", "time, .date")
                    date_el = container.select_one(date_sel) if date_sel else None
                    date_text = date_el.get("datetime", "") or date_el.get_text() if date_el else ""
                    parsed_date = self._parse_date(date_text)

                    summary_sel = self.selectors.get("summary", "p, .excerpt")
                    summary_el = container.select_one(summary_sel) if summary_sel else None
                    summary = self._clean_text(summary_el.get_text()) if summary_el else ""

                    article = {
                        "source_name": self.name,
                        "source_url": self.url,
                        "title": title,
                        "url": href,
                        "published_date": parsed_date,
                        "summary": summary,
                        "category": self._infer_category(self.name),
                        "is_headline": False,
                    }
                    articles.append(article)

                except Exception as e:
                    continue

            logger.info(f"[{self.name}] JS scrape: {len(articles)} articles")

        except Exception as e:
            logger.error(f"[{self.name}] JS scrape failed: {e}")

        return articles

    def _infer_category(self, name: str) -> str:
        name_lower = name.lower()
        if "etsy" in name_lower:
            return "etsy"
        if "jewelry" in name_lower or "jeweler" in name_lower:
            return "jewelry"
        if "fashion" in name_lower or "vogue" in name_lower or "luxury" in name_lower:
            return "fashion_luxury"
        if "google" in name_lower:
            return "news_aggregator"
        return "general"


# =============================================================================
# Scraper Factory — creates the right scraper for each source
# =============================================================================

class ScraperFactory:
    """Creates the appropriate scraper instance for each source type."""

    @staticmethod
    def create_scraper(source_name: str, source_config: dict,
                       http_client: AntiDetectClient) -> Optional[BaseSourceScraper]:
        """Factory method — returns the correct scraper for the source type."""
        source_type = source_config.get("type", "article_list")

        if source_type == "rss":
            return RSSFeedScraper(source_name, source_config, http_client)
        elif source_type == "commodity":
            return CommodityPriceScraper(source_name, source_config, http_client)
        elif source_type == "reddit":
            return RedditScraper(source_name, source_config, http_client)
        elif source_type == "js" or source_config.get("use_stealth_browser", False):
            return JavaScriptSiteScraper(source_name, source_config, http_client)
        else:
            return ArticleListScraper(source_name, source_config, http_client)


# =============================================================================
# Main Scraper — orchestrates all sources
# =============================================================================

class JewelScopeScraper:
    """
    Main orchestrator that runs all configured scrapers and collects results.
    """

    def __init__(self, config: dict, http_client: AntiDetectClient = None):
        self.config = config
        self.http_client = http_client or AntiDetectClient(config)
        self.sources = config.get("sources", {})
        self.results: Dict[str, Dict] = {}

    def run_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run all enabled scrapers and return results grouped by source.
        Returns: { source_name: [articles], ... }
        """
        results = {}
        errors = []

        for source_name, source_config in self.sources.items():
            if not source_config.get("enabled", True):
                logger.info(f"Skipping disabled source: {source_name}")
                continue

            logger.info(f"Scraping: {source_name} ({source_config.get('url', '')})")

            try:
                scraper = ScraperFactory.create_scraper(source_name, source_config, self.http_client)
                if scraper is None:
                    logger.warning(f"No scraper available for {source_name}")
                    continue

                articles = scraper.scrape()
                results[source_name] = articles
                logger.info(f"[{source_name}] Got {len(articles)} articles")

            except Exception as e:
                logger.error(f"[{source_name}] Failed: {e}")
                errors.append({"source": source_name, "error": str(e)})
                results[source_name] = []

        self.results = results
        self.errors = errors

        # Log summary
        total = sum(len(v) for v in results.values())
        logger.info(f"Scrape complete: {total} articles from {len(results)} sources "
                     f"({len(errors)} errors)")

        return results

    def get_all_articles(self) -> List[Dict[str, Any]]:
        """Flatten all articles into a single list."""
        all_articles = []
        for source_name, articles in self.results.items():
            all_articles.extend(articles)
        return all_articles

    def get_headlines(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Get top N headline articles, ranked by relevance."""
        all_articles = self.get_all_articles()

        # Score articles for headline worthiness
        def score(article):
            score = 0
            title = article.get("title", "").lower()
            summary = article.get("summary", "").lower()

            # Higher score for jewelry and market news
            high_value_terms = [
                "market", "price", "trend", "new", "launch", "acquisition",
                "merger", "record", "bestseller", "etsy update", "policy",
                "algorithm", "breakthrough", "designer", "award",
                "diamond", "gold", "platinum", "luxury", "fine jewelry",
            ]
            for term in high_value_terms:
                if term in title:
                    score += 3
                elif term in summary:
                    score += 1

            # Prefer articles with dates
            if article.get("published_date"):
                score += 1

            # Prefer articles with URLs
            if article.get("url"):
                score += 1

            return score

        all_articles.sort(key=score, reverse=True)
        return all_articles[:top_n]

    def get_commodity_prices(self) -> List[Dict[str, Any]]:
        """Get commodity price articles from the results."""
        prices = []
        for source_name, articles in self.results.items():
            for article in articles:
                if article.get("category") == "commodity":
                    prices.append(article)
        return prices

    def get_etsy_intelligence(self) -> List[Dict[str, Any]]:
        """Get Etsy-specific articles from the results."""
        etsy_articles = []
        for source_name, articles in self.results.items():
            for article in articles:
                if article.get("category") == "etsy":
                    etsy_articles.append(article)
        return etsy_articles



# =============================================================================
# Helper: load config and run
# =============================================================================

def run_scraper(config_path: str = "config.yaml") -> Dict[str, List[Dict[str, Any]]]:
    """Load config and run all scrapers. Returns results."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    client = AntiDetectClient(config)
    scraper = JewelScopeScraper(config, client)
    return scraper.run_all()
