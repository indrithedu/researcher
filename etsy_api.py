# =============================================================================
# JewelScope Research — Etsy API Integration
# =============================================================================
#
# Connects to Etsy's v3 Open API to fetch real jewelry marketplace data.
# Provides:
#   - Search active listings with jewelry filters
#   - Get listing details (title, price, images, tags, materials)
#   - Get shop info and stats
#   - Get taxonomy categories for jewelry
#   - Extract trending jewelry data
#
# API key: https://developers.etsy.com/ → Create app → Get keystring
# Free tier: 10,000 requests/day
#
# To use: set ETSY_API_KEY environment variable or pass in config
# =============================================================================

import os
import json
import time
import logging
import hashlib
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# Etsy API Configuration
# =============================================================================

ETSY_API_BASE = "https://api.etsy.com/v3"
ETSY_API_KEY = os.environ.get("ETSY_API_KEY", "")

# Rate limits: 10 requests per second, 10,000 per day
MAX_REQUESTS_PER_SECOND = 8
MAX_DAILY_REQUESTS = 9500  # Leave buffer

# Jewelry taxonomy paths (Etsy taxonomy IDs for jewelry categories)
# These are the high-level categories that contain all jewelry subcategories
JEWELRY_TAXONOMY_IDS = [
    1,     # Accessories
    97,    # Jewelry (main category)
    143,   # Fine Jewelry
    288,   # Handmade Jewelry
    314,   # Vintage Jewelry
    691,   # Engagement & Wedding
    695,   # Rings
    697,   # Necklaces
    699,   # Earrings
    701,   # Bracelets
    703,   # Jewelry Sets
    705,   # Body Jewelry
    727,   # Watches
    847,   # Loose Gemstones
    849,   # Jewelry Supplies
    1097,  # Men's Jewelry
    1177,  # Custom & Personalized Jewelry
]


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class EtsyListing:
    """An Etsy listing with jewelry-relevant fields."""
    listing_id: int
    title: str
    description: str
    price_amount: float
    price_currency: str
    taxonomy_id: int
    taxonomy_path: List[str]
    tags: List[str]
    materials: List[str]
    style: List[str]
    quantity: int
    views: int
    favorites: int
    num_sold: int
    state: str  # active, sold_out, etc.
    shop_id: int
    shop_name: str
    url: str
    main_image_url: str = ""
    created_ts: int = 0
    updated_ts: int = 0
    is_personalizable: bool = False
    is_customizable: bool = False
    is_vintage: bool = False
    is_handmade: bool = False
    production_partners: List[str] = field(default_factory=list)
    shipping_price: float = 0.0
    processing_min: int = 1
    processing_max: int = 14

    @property
    def price_category(self) -> str:
        if self.price_amount < 50:
            return "budget"
        elif self.price_amount < 200:
            return "mid_range"
        elif self.price_amount < 1000:
            return "premium"
        else:
            return "luxury"

    @property
    def engagement_score(self) -> float:
        """Combined engagement metric: views + favorites*3 + sales*10."""
        return self.views + self.favorites * 3 + self.num_sold * 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_article(self, source_name: str = "Etsy API") -> Dict[str, Any]:
        """Convert to JewelScope article format."""
        return {
            "source_name": source_name,
            "source_url": self.url,
            "title": self.title,
            "url": self.url,
            "published_date": datetime.fromtimestamp(self.updated_ts).strftime("%Y-%m-%d") if self.updated_ts else "",
            "summary": self.description[:300] if self.description else "",
            "category": "etsy",
            "is_headline": self.engagement_score > 100,
            "price": self.price_amount,
            "currency": self.price_currency,
            "tags": self.tags,
            "materials": self.materials,
            "views": self.views,
            "favorites": self.favorites,
            "sold": self.num_sold,
        }


@dataclass
class EtsyTrendReport:
    """Trending jewelry data from Etsy marketplace."""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    total_listings_analyzed: int = 0

    # Top selling categories
    top_categories: List[Dict] = field(default_factory=list)

    # Price trends by category
    avg_price_by_category: Dict[str, float] = field(default_factory=dict)
    price_range_by_category: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    # Material trends
    top_materials: List[Dict] = field(default_factory=list)

    # Tag/keyword trends
    top_tags: List[Dict] = field(default_factory=list)

    # Style trends
    top_styles: Dict[str, int] = field(default_factory=dict)

    # High-engagement listings (rising stars)
    rising_stars: List[Dict] = field(default_factory=list)

    # Price correlation analysis
    price_vs_demand: Dict[str, float] = field(default_factory=dict)

    # Shop analysis
    top_shops: List[Dict] = field(default_factory=list)

    # Listing health metrics
    avg_views_per_listing: float = 0.0
    avg_favorites_per_listing: float = 0.0
    avg_sold_per_listing: float = 0.0

    # Time-based trends
    new_listings_today: int = 0
    sold_out_listings: int = 0

    def format_summary(self) -> str:
        """Format as a readable summary."""
        lines = []
        lines.append(f"🛒 **Etsy Marketplace Report** — {self.generated_at[:10]}")
        lines.append(f"   Listings analyzed: {self.total_listings_analyzed}")
        lines.append("")

        lines.append(f"📊 **Average prices:**")
        for cat, price in sorted(self.avg_price_by_category.items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"   - {cat}: ${price:.2f}")

        lines.append(f"\n🔥 **Top materials:**")
        for m in self.top_materials[:8]:
            lines.append(f"   - {m['material']}: {m['count']} listings ({m.get('avg_price', 0):.0f} avg)")

        lines.append(f"\n🏷️ **Top tags:**")
        for t in self.top_tags[:10]:
            lines.append(f"   - #{t['tag']}: {t['count']} listings")

        lines.append(f"\n⭐ **Rising stars (high engagement):**")
        for ls in self.rising_stars[:5]:
            lines.append(f"   - {ls.get('title', 'Untitled')[:60]} — {ls.get('favorites', 0)} ❤️")

        return "\n".join(lines)


# =============================================================================
# Etsy API Client
# =============================================================================

class EtsyAPIClient:
    """
    Client for Etsy's v3 Open API.
    
    Handles:
    - Rate limiting (8 req/sec, 9500 req/day)
    - Pagination (100 listings per page)
    - Error handling with retries
    - Caching to avoid redundant calls
    - API key management
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or ETSY_API_KEY
        if not self.api_key:
            logger.warning("No ETSY_API_KEY set — Etsy integration will be disabled")

        # Rate limiting
        self._request_timestamps: List[float] = []
        self._daily_count = 0
        self._daily_reset = datetime.utcnow() + timedelta(days=1)

        # Cache: {url: (timestamp, data)}
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self.cache_ttl = 300  # 5 minutes for listings, longer for taxonomy

        # Stats
        self.stats = {"requests": 0, "cache_hits": 0, "errors": 0}

    def _check_rate_limit(self):
        """Ensure we don't exceed Etsy's rate limits."""
        now = datetime.utcnow()

        # Daily reset
        if now > self._daily_reset:
            self._daily_count = 0
            self._daily_reset = now + timedelta(days=1)

        if self._daily_count >= MAX_DAILY_REQUESTS:
            logger.warning(f"Daily request limit reached ({MAX_DAILY_REQUESTS})")
            return False

        # Per-second rate limiting
        cutoff = now.timestamp() - 1.0
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
        if len(self._request_timestamps) >= MAX_REQUESTS_PER_SECOND:
            sleep_time = 1.0 - (now.timestamp() - self._request_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

        return True

    def _get_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Accept": "application/json",
        }

    def request(self, endpoint: str, params: Dict = None,
                method: str = "GET", use_cache: bool = True) -> Optional[Dict]:
        """
        Make an API request with rate limiting and caching.
        
        Args:
            endpoint: API path (e.g., "/application/listings/active")
            params: Query parameters
            method: HTTP method
            use_cache: Whether to cache the response
            
        Returns:
            Parsed JSON response, or None on failure
        """
        if not self.api_key:
            logger.warning("Etsy API key not configured")
            return None

        url = f"{ETSY_API_BASE}{endpoint}"
        param_hash = hashlib.md5(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()
        cache_key = f"{url}:{param_hash}"

        # Check cache
        if use_cache and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.time() - ts < self.cache_ttl:
                self.stats["cache_hits"] += 1
                return data

        # Rate limit check
        if not self._check_rate_limit():
            return None

        self._request_timestamps.append(time.time())
        self._daily_count += 1
        self.stats["requests"] += 1

        try:
            if method == "GET":
                resp = httpx.get(url, headers=self._get_headers(), params=params, timeout=15)
            elif method == "POST":
                resp = httpx.post(url, headers=self._get_headers(), json=params, timeout=15)
            else:
                return None

            if resp.status_code == 200:
                data = resp.json()
                if use_cache:
                    self._cache[cache_key] = (time.time(), data)
                return data

            elif resp.status_code == 401:
                logger.error("Invalid Etsy API key")
                return None

            elif resp.status_code == 429:
                retry = int(resp.headers.get("retry-after", 5))
                logger.warning(f"Etsy rate limited — waiting {retry}s")
                time.sleep(retry)
                return self.request(endpoint, params, method, use_cache)

            elif resp.status_code == 403:
                logger.error(f"Etsy access denied to {endpoint}")
                return None

            else:
                logger.warning(f"Etsy API returned {resp.status_code} for {endpoint}")
                self.stats["errors"] += 1
                return None

        except httpx.TimeoutException:
            logger.warning(f"Etsy API timeout: {endpoint}")
            self.stats["errors"] += 1
            return None
        except Exception as e:
            logger.error(f"Etsy API error: {endpoint} — {e}")
            self.stats["errors"] += 1
            return None

    # -----------------------------------------------------------------------
    # Listings
    # -----------------------------------------------------------------------

    def search_jewelry_listings(self, query: str = "", category: str = "",
                                 min_price: float = None, max_price: float = None,
                                 sort: str = "score", limit: int = 100,
                                 page: int = 1) -> List[EtsyListing]:
        """
        Search for jewelry listings on Etsy.
        
        Args:
            query: Search query (e.g., "gold ring", "silver necklace")
            category: Taxonomy path or ID
            min_price: Minimum price
            max_price: Maximum price
            sort: "score" (relevance), "price", "created", "shipping", etc.
            limit: Results per page (max 100)
            page: Page number
            
        Returns:
            List of EtsyListing objects
        """
        params = {
            "limit": min(limit, 100),
            "sort_on": sort,
            "page": page,
        }

        if query:
            params["keywords"] = query
        if min_price is not None:
            params["min_price"] = min_price
        if max_price is not None:
            params["max_price"] = max_price

        # Use taxonomy for jewelry category
        if category and category.isdigit():
            params["taxonomy_id"] = category

        data = self.request("/application/listings/active", params)
        if not data:
            return []

        return self._parse_listings(data)

    def _parse_listings(self, data: Dict) -> List[EtsyListing]:
        """Parse API response into EtsyListing objects."""
        listings = []
        results = data.get("results", []) or data.get("data", []) or []

        for item in results:
            try:
                listing = EtsyListing(
                    listing_id=item.get("listing_id", 0),
                    title=item.get("title", ""),
                    description=item.get("description", "") or "",
                    price_amount=float(item.get("price", {}).get("amount", 0) or 0),
                    price_currency=item.get("price", {}).get("currency_code", "USD"),
                    taxonomy_id=item.get("taxonomy_id", 0),
                    taxonomy_path=item.get("taxonomy_path", []),
                    tags=item.get("tags", []) or [],
                    materials=item.get("materials", []) or [],
                    style=item.get("style", []) or [],
                    quantity=item.get("quantity", 0),
                    views=item.get("views", 0) or 0,
                    favorites=item.get("num_favorers", 0) or 0,
                    num_sold=item.get("sold_out", False) if not item.get("num_sold") else int(item.get("num_sold", 0)),
                    state=item.get("state", "active"),
                    shop_id=item.get("shop_id", 0),
                    shop_name=item.get("Shop", {}).get("shop_name", "") if isinstance(item.get("Shop"), dict) else "",
                    url=item.get("url", "") or f"https://www.etsy.com/listing/{item.get('listing_id', 0)}",
                    created_ts=item.get("created_tsz", 0),
                    updated_ts=item.get("last_modified_tsz", 0),
                    is_vintage=item.get("is_vintage", False),
                    is_handmade=True,  # Most Etsy jewelry is handmade
                    shipping_price=float(item.get("shipping_profile", {}).get("primary_cost", {}).get("amount", 0) or 0)
                    if isinstance(item.get("shipping_profile"), dict) else 0.0,
                )
                listings.append(listing)
            except Exception as e:
                logger.debug(f"Error parsing Etsy listing: {e}")
                continue

        return listings

    # -----------------------------------------------------------------------
    # Taxonomy
    # -----------------------------------------------------------------------

    def get_taxonomy_nodes(self, taxonomy_id: int = None, use_cache: bool = True) -> Optional[Dict]:
        """Get Etsy taxonomy tree for category browsing."""
        if taxonomy_id:
            endpoint = f"/application/market/taxonomy/nodes/{taxonomy_id}"
        else:
            endpoint = "/application/market/taxonomy/nodes"

        data = self.request(endpoint, use_cache=use_cache)
        return data

    def get_jewelry_taxonomy(self) -> Dict[str, Any]:
        """Get full jewelry taxonomy tree from Etsy."""
        taxonomy = {}
        for tid in JEWELRY_TAXONOMY_IDS:
            data = self.get_taxonomy_nodes(tid)
            if data:
                results = data.get("results", []) or [data]
                for r in results:
                    name = r.get("name", f"Category_{tid}")
                    path = r.get("full_path_taxonomy_ids", [])
                    taxonomy[name] = {
                        "id": tid,
                        "path": path,
                        "children_count": len(r.get("children", [])),
                    }
        return taxonomy

    # -----------------------------------------------------------------------
    # Listings Images
    # -----------------------------------------------------------------------

    def get_listing_images(self, listing_id: int) -> List[str]:
        """Get image URLs for a listing."""
        data = self.request(f"/application/listings/{listing_id}/images")
        if not data:
            return []

        images = []
        for img in data.get("results", []) or data.get("data", []) or []:
            url = img.get("url_fullxfull", img.get("url_570xN", ""))
            if url:
                images.append(url)
        return images

    # -----------------------------------------------------------------------
    # Shop details
    # -----------------------------------------------------------------------

    def get_shop(self, shop_id: int) -> Optional[Dict]:
        """Get shop details."""
        return self.request(f"/application/shops/{shop_id}")

    def get_shop_listings(self, shop_id: int, limit: int = 50) -> List[EtsyListing]:
        """Get all active listings for a shop."""
        data = self.request(f"/application/shops/{shop_id}/listings/active",
                           {"limit": min(limit, 100)})
        if not data:
            return []
        return self._parse_listings(data)


# =============================================================================
# Etsy Trend Analyzer
# =============================================================================

class EtsyTrendAnalyzer:
    """
    Analyzes Etsy marketplace data to extract jewelry trends.
    
    Processes raw listing data into structured trend reports:
    - Material popularity over time
    - Price trends by category
    - Tag/keyword frequency analysis
    - High-engagement "rising star" listings
    - Shop performance metrics
    """

    def __init__(self, api_client: EtsyAPIClient = None):
        self.api = api_client or EtsyAPIClient()
        self.listings: List[EtsyListing] = []

    def fetch_multiple_categories(self, queries: List[str] = None,
                                   listings_per_query: int = 50) -> List[EtsyListing]:
        """
        Fetch listings across multiple jewelry categories/queries.
        
        Default queries cover the full jewelry landscape.
        """
        if queries is None:
            queries = [
                "ring", "necklace", "earrings", "bracelet",
                "gold jewelry", "silver jewelry", "diamond jewelry",
                "handmade jewelry", "fine jewelry", "vintage jewelry",
                "engagement ring", "wedding band",
                "gemstone ring", "pearl necklace",
                "men's jewelry", "custom jewelry",
                "birthstone jewelry", "personalized jewelry",
            ]

        all_listings = []
        for query in queries:
            logger.info(f"Fetching Etsy listings: '{query}'...")
            listings = self.search_jewelry(query=query, limit=listings_per_query)
            all_listings.extend(listings)

        # Deduplicate by listing_id
        seen = set()
        unique = []
        for l in all_listings:
            if l.listing_id not in seen:
                seen.add(l.listing_id)
                unique.append(l)

        self.listings = unique
        logger.info(f"Total unique Etsy listings: {len(unique)}")
        return unique

    def search_jewelry(self, query: str = "", limit: int = 100) -> List[EtsyListing]:
        """Search and return jewelry listings."""
        return self.api.search_jewelry_listings(query=query, limit=limit)

    def analyze_trends(self) -> EtsyTrendReport:
        """Run full trend analysis on collected listings."""
        report = EtsyTrendReport()
        report.total_listings_analyzed = len(self.listings)

        if not self.listings:
            logger.warning("No listings to analyze")
            return report

        # Category analysis
        cat_counter = Counter()
        cat_prices = defaultdict(list)
        for l in self.listings:
            if l.taxonomy_path:
                path = l.taxonomy_path[-1] if l.taxonomy_path else "unknown"
                cat_counter[path] += 1
                cat_prices[path].append(l.price_amount)

        report.top_categories = [
            {"category": cat, "count": count, "pct": count / len(self.listings) * 100}
            for cat, count in cat_counter.most_common(15)
        ]
        report.avg_price_by_category = {
            cat: sum(prices) / len(prices)
            for cat, prices in cat_prices.items()
            if prices
        }

        # Material analysis
        material_data = defaultdict(lambda: {"count": 0, "prices": [], "total_sold": 0})
        for l in self.listings:
            for mat in l.materials:
                m = mat.lower().strip()
                material_data[m]["count"] += 1
                material_data[m]["prices"].append(l.price_amount)
                material_data[m]["total_sold"] += l.num_sold

        report.top_materials = [
            {
                "material": mat,
                "count": d["count"],
                "pct": d["count"] / len(self.listings) * 100,
                "avg_price": sum(d["prices"]) / len(d["prices"]) if d["prices"] else 0,
                "total_sold": d["total_sold"],
            }
            for mat, d in sorted(material_data.items(),
                                  key=lambda x: x[1]["count"], reverse=True)[:30]
        ]

        # Tag analysis
        tag_counter = Counter()
        for l in self.listings:
            for tag in l.tags:
                tag_counter[tag.lower().strip()] += 1

        report.top_tags = [
            {"tag": tag, "count": count}
            for tag, count in tag_counter.most_common(30)
        ]

        # Style analysis
        style_counter = Counter()
        for l in self.listings:
            for s in l.style:
                style_counter[s.lower().strip()] += 1
        report.top_styles = dict(style_counter.most_common(10))

        # Rising stars (high engagement relative to listing age)
        now = time.time()
        scored = []
        for l in self.listings:
            if l.created_ts > 0:
                age_days = (now - l.created_ts) / 86400
                if age_days < 90:  # Listed in last 90 days
                    daily_engagement = l.engagement_score / max(age_days, 1)
                    scored.append((daily_engagement, l))

        scored.sort(key=lambda x: x[0], reverse=True)
        report.rising_stars = [l.to_dict() for _, l in scored[:20]]

        # Top shops
        shop_counter = Counter()
        shop_sales = defaultdict(int)
        for l in self.listings:
            if l.shop_name:
                shop_counter[l.shop_name] += 1
                shop_sales[l.shop_name] += l.num_sold

        report.top_shops = [
            {"shop": shop, "listings": count, "total_sold": shop_sales[shop]}
            for shop, count in shop_counter.most_common(20)
        ]

        # Price vs demand analysis
        price_brackets = defaultdict(lambda: {"count": 0, "total_engagement": 0})
        for l in self.listings:
            bucket = l.price_category
            price_brackets[bucket]["count"] += 1
            price_brackets[bucket]["total_engagement"] += l.engagement_score

        report.price_vs_demand = {
            bucket: d["total_engagement"] / max(d["count"], 1)
            for bucket, d in price_brackets.items()
        }

        # Aggregate metrics
        if self.listings:
            report.avg_views_per_listing = sum(l.views for l in self.listings) / len(self.listings)
            report.avg_favorites_per_listing = sum(l.favorites for l in self.listings) / len(self.listings)
            report.avg_sold_per_listing = sum(l.num_sold for l in self.listings) / len(self.listings)
            report.new_listings_today = sum(
                1 for l in self.listings
                if l.created_ts > (time.time() - 86400)
            )
            report.sold_out_listings = sum(1 for l in self.listings if l.state == "sold_out")

        return report


# =============================================================================
# Quick test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Etsy API Integration — JewelScope Research")
    print("=" * 60)

    key = os.environ.get("ETSY_API_KEY", "")
    if not key:
        print("\n⚠️  No ETSY_API_KEY set.")
        print("   To use: export ETSY_API_KEY='your_key_here'")
        print("   Get a key: https://developers.etsy.com/ → Create App\n")
        print("   Running in DEMO mode with sample data predictions...")

        # Generate synthetic listings for demonstration
        demo = EtsyTrendReport()
        import random
        random.seed(42)

        demo.total_listings_analyzed = 500
        demo.top_categories = [
            {"category": "Rings", "count": 150, "pct": 30.0},
            {"category": "Necklaces", "count": 110, "pct": 22.0},
            {"category": "Earrings", "count": 95, "pct": 19.0},
            {"category": "Bracelets", "count": 75, "pct": 15.0},
            {"category": "Body Jewelry", "count": 35, "pct": 7.0},
            {"category": "Watches", "count": 20, "pct": 4.0},
            {"category": "Jewelry Sets", "count": 15, "pct": 3.0},
        ]
        demo.avg_price_by_category = {
            "Rings": 185.50, "Necklaces": 95.00, "Earrings": 65.00,
            "Bracelets": 120.00, "Body Jewelry": 25.00, "Watches": 450.00,
        }
        demo.top_materials = [
            {"material": "sterling silver", "count": 180, "avg_price": 85.00, "total_sold": 1200},
            {"material": "gold", "count": 120, "avg_price": 250.00, "total_sold": 800},
            {"material": "stainless steel", "count": 85, "avg_price": 45.00, "total_sold": 650},
            {"material": "diamond", "count": 65, "avg_price": 450.00, "total_sold": 300},
            {"material": "rose gold", "count": 55, "avg_price": 195.00, "total_sold": 420},
            {"material": "pearl", "count": 45, "avg_price": 120.00, "total_sold": 280},
            {"material": "gemstone", "count": 40, "avg_price": 175.00, "total_sold": 350},
        ]
        demo.top_tags = [
            {"tag": "handmade", "count": 320},
            {"tag": "gift for her", "count": 280},
            {"tag": "personalized", "count": 195},
            {"tag": "sterling silver", "count": 180},
            {"tag": "birthday gift", "count": 165},
            {"tag": "engagement", "count": 120},
            {"tag": "wedding", "count": 110},
            {"tag": "anniversary", "count": 95},
        ]
        demo.avg_views_per_listing = 1250
        demo.avg_favorites_per_listing = 45
        demo.avg_sold_per_listing = 12.5

        print(demo.format_summary())
        print("\n✅ Demo data generated. Set ETSY_API_KEY for real data.\n")
    else:
        print(f"\n✅ ETSY_API_KEY configured ({key[:8]}...{key[-4:]})")
        print("Fetching real Etsy data...")

        client = EtsyAPIClient(key)
        analyzer = EtsyTrendAnalyzer(client)

        listings = analyzer.fetch_multiple_categories(listings_per_query=20)
        print(f"Fetched {len(listings)} listings")

        report = analyzer.analyze_trends()
        print(report.format_summary())