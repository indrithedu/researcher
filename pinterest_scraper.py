# =============================================================================
# JewelScope Research — Pinterest Trend Scraper
# =============================================================================
#
# Scrapes Pinterest search results for fine jewelry trends.
# Uses the existing Playwright stealth browser from anti_detect.py
# to handle Pinterest's JavaScript-heavy rendering.
#
# Pinterest search provides:
#   - Popular pins by search term (engagement, saves, comments)
#   - Visual trend detection (what styles are being saved/pinned)
#   - Board/shop discovery
#
# No API key needed — uses public Pinterest search pages.
# Rate limit: ~30 searches/hour (Pinterest will block IP if faster)
# =============================================================================

import re
import json
import logging
import time
import random
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


# =============================================================================
# Jewelry search terms for Pinterest trend tracking
# =============================================================================

PINTEREST_SEARCH_TERMS = [
    "fine jewelry", "gold jewelry", "diamond ring", "engagement ring",
    "gold necklace", "layered necklace", "tennis bracelet",
    "hoop earrings", "stud earrings", "gemstone ring",
    "rose gold jewelry", "moissanite ring", "vintage jewelry",
    "minimalist jewelry", "stackable rings", "bridal jewelry",
    "pearl necklace", "gold chain", "custom jewelry",
]

# Pinterest search base URL
PINTEREST_SEARCH_URL = "https://www.pinterest.com/search/pins/?q={q}&rs=typed"


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PinterestPin:
    """A single Pinterest pin with jewelry-relevant fields."""
    pin_id: str
    title: str
    description: str
    image_url: str
    pin_url: str
    board_name: str = ""
    repin_count: int = 0
    save_count: int = 0
    comment_count: int = 0
    search_term: str = ""
    scraped_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @property
    def engagement_score(self) -> int:
        return self.repin_count + self.save_count * 2 + self.comment_count * 3


@dataclass
class PinterestTrendReport:
    """Trend insights from Pinterest scraping."""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    scan_date: str = field(default_factory=lambda: date.today().isoformat())
    total_pins_collected: int = 0
    search_terms_scraped: int = 0

    # Top trending terms (by pin volume/engagement)
    trending_terms: List[Dict] = field(default_factory=list)

    # Top engaged pins across all searches
    top_pins: List[Dict] = field(default_factory=list)

    # Most common materials/styles mentioned in pins
    top_keywords: List[Dict] = field(default_factory=list)

    # Board insights
    top_boards: List[Dict] = field(default_factory=list)

    # Category breakdown
    style_distribution: Dict[str, int] = field(default_factory=dict)

    def format_summary(self) -> str:
        lines = []
        lines.append(f"📌 **Pinterest Jewelry Trends** — {self.scan_date}")
        lines.append(f"   {self.total_pins_collected} pins across {self.search_terms_scraped} searches")
        lines.append("")

        if self.trending_terms:
            lines.append("🔥 **Trending search terms:**")
            for t in self.trending_terms[:5]:
                lines.append(f"   • {t['term']}: {t.get('avg_engagement', 0):.0f} avg engagement")

        if self.top_pins:
            lines.append("\n⭐ **Top pins:**")
            for p in self.top_pins[:5]:
                lines.append(f"   • {p.get('title', '')[:50]} — {p.get('save_count', 0)} saves")

        return "\n".join(lines)


# =============================================================================
# Pinterest Scraper
# =============================================================================

class PinterestTrendScraper:
    """
    Scrapes Pinterest for fine jewelry trend data.
    
    Uses Playwright stealth browser (from anti_detect.py) to handle
    Pinterest's JavaScript rendering and anti-bot protection.
    
    Strategy:
    1. Search Pinterest for each jewelry term
    2. Wait for pin grid to load
    3. Extract pin data (title, saves, image, board)
    4. Aggregate into trend report
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.pins: List[PinterestPin] = []
        self.errors: List[str] = []

    def scrape_all_terms(self, terms: List[str] = None) -> PinterestTrendReport:
        """Scrape Pinterest for all jewelry search terms."""
        report = PinterestTrendReport()
        terms = terms or PINTEREST_SEARCH_TERMS
        report.search_terms_scraped = len(terms)

        all_pins = []
        for term in terms:
            try:
                pins = self._scrape_term(term)
                all_pins.extend(pins)
                logger.info(f"Pinterest '{term}': {len(pins)} pins")
                # Be respectful — delay between searches
                time.sleep(random.uniform(3, 6))
            except Exception as e:
                logger.warning(f"Pinterest scrape failed for '{term}': {e}")
                self.errors.append(f"{term}: {e}")

        self.pins = all_pins
        report.total_pins_collected = len(all_pins)

        if not all_pins:
            return report

        # ---- Trending terms ----
        term_metrics = defaultdict(list)
        for pin in all_pins:
            term_metrics[pin.search_term].append(pin.engagement_score)

        report.trending_terms = [
            {"term": term, "count": len(scores),
             "avg_engagement": sum(scores) / len(scores),
             "total_engagement": sum(scores)}
            for term, scores in sorted(term_metrics.items(),
                                       key=lambda x: sum(x[1]), reverse=True)
        ]

        # ---- Top pins ----
        all_pins_sorted = sorted(all_pins, key=lambda p: p.engagement_score, reverse=True)
        report.top_pins = [p.to_dict() for p in all_pins_sorted[:20]]

        # ---- Common keywords in titles ----
        word_counter = Counter()
        jewelry_terms = ["gold", "silver", "diamond", "ring", "necklace", "earring",
                         "bracelet", "rose", "white", "yellow", "vintage", "modern",
                         "minimalist", "stackable", "layered", "charm", "pendant",
                         "hoop", "stud", "tennis", "bangle", "cuff", "chain",
                         "pearl", "gemstone", "moissanite", "sapphire", "emerald",
                         "engagement", "wedding", "bridal", "custom", "personalized",
                         "handmade", "artisan", "boho", "statement", "dainty",
                         "chunky", "thick", "thin", "delicate", "bold"]
        for pin in all_pins:
            text = f"{pin.title} {pin.description}".lower()
            for term in jewelry_terms:
                if term in text:
                    word_counter[term] += 1

        report.top_keywords = [
            {"keyword": word, "count": count,
             "pct": round(count / len(all_pins) * 100, 1)}
            for word, count in word_counter.most_common(20)
        ]

        # ---- Top boards ----
        board_counter = Counter()
        for pin in all_pins:
            if pin.board_name:
                board_counter[pin.board_name] += 1
        report.top_boards = [
            {"board": board, "count": count}
            for board, count in board_counter.most_common(15)
        ]

        # ---- Style distribution ----
        style_keywords = {
            "Vintage": ["vintage", "antique", "retro", "old"],
            "Modern": ["modern", "contemporary", "minimalist", "sleek"],
            "Boho": ["boho", "bohemian", "hippie", "earthy"],
            "Statement": ["statement", "bold", "chunky", "oversized"],
            "Dainty": ["dainty", "delicate", "thin", "fine"],
            "Layered": ["layered", "stackable", "stacking"],
            "Custom": ["custom", "personalized", "engraved", "initial"],
            "Bridal": ["bridal", "wedding", "engagement", "bridesmaid"],
        }
        style_counts = defaultdict(int)
        for pin in all_pins:
            text = f"{pin.title} {pin.description}".lower()
            for style, keywords in style_keywords.items():
                if any(kw in text for kw in keywords):
                    style_counts[style] += 1
        report.style_distribution = dict(style_counts)

        logger.info(f"Pinterest: {len(all_pins)} pins, "
                    f"{len(report.trending_terms)} trending terms, "
                    f"{len(report.errors)} errors")
        return report

    def _scrape_term(self, term: str) -> List[PinterestPin]:
        """
        Scrape Pinterest search results for a single term.
        
        Uses Playwright stealth browser to handle JS rendering.
        Falls back to basic HTTP if Playwright unavailable.
        """
        from anti_detect import StealthBrowser

        pins = []
        url = PINTEREST_SEARCH_URL.format(q=quote_plus(term))

        # Use StealthBrowser for JavaScript-heavy Pinterest
        browser = StealthBrowser(self.config.get("anti_detection", {}))
        page_content = browser.get_page_source(url, wait_selector='[data-test-id="pin"]',
                                                wait_timeout=15000)

        if not page_content:
            logger.warning(f"Pinterest: no content for '{term}'")
            return pins

        # Try to extract pin data from the page
        pins = self._extract_pins_from_html(page_content, term)
        browser.close()

        return pins

    def _extract_pins_from_html(self, html: str, search_term: str) -> List[PinterestPin]:
        """Extract pin data from Pinterest search HTML."""
        pins = []

        # Pinterest embeds pin data in script tags with __INITIAL_STATE__
        # Also try to find pin data in JSON-LD or data attributes
        patterns = [
            r'__INITIAL_STATE__\s*=\s*({.*?});',
            r'"pins":\s*(\[.*?\])',
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>({.*?})</script>',
        ]

        pin_data = None
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    pin_data = json.loads(match.group(1))
                    break
                except json.JSONDecodeError:
                    continue

        if pin_data:
            # Navigate the complex Pinterest state tree
            pins = self._parse_pinterest_state(pin_data, search_term)

        # Fallback: try extracting from HTML data attributes
        if not pins:
            pins = self._extract_from_html_fallback(html, search_term)

        return pins

    def _parse_pinterest_state(self, state: dict, search_term: str) -> List[PinterestPin]:
        """Parse pin data from Pinterest's __INITIAL_STATE__ structure."""
        pins = []

        # Pinterest state is deeply nested — try common paths
        try:
            # Try resources path
            resources = state.get("resources", {})
            for key, data in resources.items():
                if isinstance(data, dict):
                    for resource_id, resource_data in data.items():
                        if isinstance(resource_data, dict):
                            data_field = resource_data.get("data", {})
                            results = data_field.get("results", [])
                            if isinstance(results, list):
                                for item in results:
                                    pin = self._parse_pin_item(item, search_term)
                                    if pin:
                                        pins.append(pin)
        except Exception as e:
            logger.debug(f"Pinterest state parse: {e}")

        return pins

    def _parse_pin_item(self, item: dict, search_term: str) -> Optional[PinterestPin]:
        """Parse a single pin item from Pinterest data."""
        try:
            pin_id = str(item.get("id", ""))
            if not pin_id:
                return None

            # Pinterest data uses various field names
            title = (item.get("title", "") or
                     item.get("description", "") or
                     item.get("grid_description", "") or "")

            description = (item.get("description", "") or
                          item.get("rich_description", "") or
                          item.get("seo_description", "") or "")

            # Try to get the best title — Pinterest often has it in native_creator
            if not title and "native_creator" in item:
                creator = item["native_creator"]
                if isinstance(creator, dict):
                    title = creator.get("full_name", "") or creator.get("username", "")

            images = item.get("images", {}) or {}
            image_url = ""
            for size_key in ["orig", "736x", "564x", "236x"]:
                if size_key in images:
                    img_data = images[size_key]
                    if isinstance(img_data, dict):
                        image_url = img_data.get("url", "")
                        break
                    elif isinstance(img_data, list) and img_data:
                        image_url = img_data[0].get("url", "")

            board_name = ""
            board_data = item.get("board", {})
            if isinstance(board_data, dict):
                board_name = board_data.get("name", "")

            repin_count = int(item.get("repin_count", 0) or 0)
            save_count = int(item.get("save_count", 0) or 0) or repin_count
            comment_count = int(item.get("comment_count", 0) or 0)

            pin_url = item.get("link", "") or item.get("url", "") or ""
            if not pin_url:
                pin_url = f"https://www.pinterest.com/pin/{pin_id}/"

            return PinterestPin(
                pin_id=pin_id,
                title=title[:200] if title else "",
                description=description[:300] if description else "",
                image_url=image_url,
                pin_url=pin_url,
                board_name=board_name,
                repin_count=repin_count,
                save_count=save_count,
                comment_count=comment_count,
                search_term=search_term,
                scraped_at=datetime.utcnow().isoformat(),
            )
        except Exception as e:
            logger.debug(f"Pin parse error: {e}")
            return None

    def _extract_from_html_fallback(self, html: str, search_term: str) -> List[PinterestPin]:
        """Fallback: extract pin data from HTML data attributes."""
        pins = []

        # Try to find pin containers by common Pinterest CSS patterns
        pin_patterns = [
            r'<div[^>]*data-test-id="pin"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*pin[^"]*"[^>]*>(.*?)</div>',
        ]

        for pattern in pin_patterns:
            containers = re.findall(pattern, html, re.DOTALL)
            if containers:
                for container in containers:
                    # Extract image URL
                    img_match = re.search(r'<img[^>]*src="([^"]+)"', container)
                    image_url = img_match.group(1) if img_match else ""

                    # Extract alt text (often contains title)
                    alt_match = re.search(r'alt="([^"]*)"', container)
                    title = alt_match.group(1) if alt_match else ""

                    if image_url or title:
                        pin = PinterestPin(
                            pin_id=f"pin_{hash(container) % 10**8}",
                            title=title[:200] if title else "",
                            description="",
                            image_url=image_url,
                            pin_url="",
                            board_name="",
                            repin_count=0,
                            save_count=0,
                            comment_count=0,
                            search_term=search_term,
                            scraped_at=datetime.utcnow().isoformat(),
                        )
                        pins.append(pin)

                if pins:
                    break  # Stop if we found pins with this pattern

        return pins


# =============================================================================
# Standalone usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Pinterest Trend Scraper — JewelScope Research")
    print("=" * 60)

    scraper = PinterestTrendScraper()
    report = scraper.scrape_all_terms(["gold ring", "diamond earrings"])
    print(report.format_summary())

    if report.top_pins:
        print(f"\nTop pin: {report.top_pins[0].get('title', 'N/A')}")
    if report.top_keywords:
        print(f"Top keyword: {report.top_keywords[0]}")
    print(f"Errors: {len(scraper.errors)}")