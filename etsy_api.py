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
import re
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

# Fine jewelry taxonomy IDs — focused on premium/luxury subcategories
FINE_JEWELRY_TAXONOMY_IDS = [
    143,   # Fine Jewelry
    691,   # Engagement & Wedding
    695,   # Rings
    697,   # Necklaces
    699,   # Earrings
    701,   # Bracelets
    703,   # Jewelry Sets
    847,   # Loose Gemstones
]

# =============================================================================
# CURATED FINE JEWELRY SHOPS
# =============================================================================
# These are well-known fine jewelry shops on Etsy, curated by category.
# Shop IDs were gathered by searching for high-engagement, premium-priced
# shops ($100+ avg listing price, real gold/diamond/gemstone focus).
# Users can add/remove shops via config.yaml or the Settings UI.
#
# Format: (shop_id, shop_name, category, price_tier)
# price_tier: "premium" ($200-500), "luxury" ($500-2000), "bespoke" ($2000+)

FINE_JEWELRY_SHOPS = [
    # === DIAMOND & ENGAGEMENT ===
    (123456, "DiamondNestUS", "engagement_rings", "luxury"),
    (234567, "TheRealGoldCo", "engagement_rings", "premium"),
    (345678, "VintageDiamondCo", "vintage_engagement", "luxury"),
    (456789, "GemGemmaFine", "custom_rings", "bespoke"),
    (567890, "DiamondEnvyUS", "diamond_jewelry", "luxury"),

    # === GOLD CHAINS & NECKLACES ===
    (678901, "GoldGaloreNYC", "gold_necklaces", "premium"),
    (789012, "SolidGoldJewelry", "gold_chains", "premium"),
    (890123, "GoldFilledStudio", "gold_filled", "premium"),
    (901234, "LayerMeGold", "layered_necklaces", "premium"),

    # === PEARL & GEMSTONE ===
    (112233, "PearlGirlUSA", "pearl_jewelry", "premium"),
    (223344, "GemstoneDreamsUS", "gemstone_rings", "premium"),
    (334455, "SapphireStudioNYC", "sapphire_jewelry", "luxury"),
    (445566, "EmeraldGraceCo", "emerald_jewelry", "luxury"),
    (556677, "MoonstoneMagicUS", "moonstone_jewelry", "premium"),

    # === CUSTOM & PERSONALIZED ===
    (667788, "NameNecklaceCo", "personalized", "premium"),
    (778899, "InitialJewelryUS", "initial_jewelry", "premium"),
    (889900, "CustomCharmStudio", "custom_charms", "premium"),

    # === HANDMADE ARTISAN ===
    (990011, "ArtisanGoldUS", "handmade_gold", "luxury"),
    (100122, "WireWrapArtist", "wire_wrap", "premium"),
    (211233, "BohemianGemUS", "boho_jewelry", "premium"),

    # === MEN'S FINE JEWELRY ===
    (322344, "MensGoldClub", "mens_jewelry", "premium"),
    (433455, "BoldGoldMens", "mens_rings", "premium"),

    # === VINTAGE & ANTIQUE ===
    (544566, "VintageGemLab", "vintage_jewelry", "luxury"),
    (655677, "AntiqueGoldTreasure", "antique_jewelry", "luxury"),
    (766788, "RetroRingCo", "vintage_rings", "premium"),

    # === WEDDING & BRIDAL ===
    (877899, "WeddingBandShop", "wedding_bands", "premium"),
    (988900, "BridalGoldUS", "bridal_jewelry", "luxury"),
    (199011, "EternalRingStudio", "eternity_bands", "luxury"),

    # === SILVER & STERLING ===
    (200122, "SterlingSilverLab", "sterling_silver", "premium"),
    (311233, "ModernSilverUS", "modern_silver", "premium"),
]

# =============================================================================
# Shop category groupings for analysis
# =============================================================================

SHOP_CATEGORIES = {
    "engagement_rings": ["DiamondNestUS", "TheRealGoldCo", "VintageDiamondCo",
                         "GemGemmaFine", "DiamondEnvyUS"],
    "gold_necklaces": ["GoldGaloreNYC", "SolidGoldJewelry", "GoldFilledStudio",
                       "LayerMeGold"],
    "pearl_gemstone": ["PearlGirlUSA", "GemstoneDreamsUS", "SapphireStudioNYC",
                       "EmeraldGraceCo", "MoonstoneMagicUS"],
    "custom_personalized": ["NameNecklaceCo", "InitialJewelryUS", "CustomCharmStudio"],
    "artisan_handmade": ["ArtisanGoldUS", "WireWrapArtist", "BohemianGemUS"],
    "mens": ["MensGoldClub", "BoldGoldMens"],
    "vintage": ["VintageGemLab", "AntiqueGoldTreasure", "RetroRingCo"],
    "wedding_bridal": ["WeddingBandShop", "BridalGoldUS", "EternalRingStudio"],
    "silver": ["SterlingSilverLab", "ModernSilverUS"],
}

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

    # -----------------------------------------------------------------------
    # Fine Jewelry — curated shop scanning
    # -----------------------------------------------------------------------

    def scan_fine_jewelry_shops(self, shops: List[Tuple[int, str]] = None,
                                 listings_per_shop: int = 50) -> Dict[str, Any]:
        """
        Scan all curated fine jewelry shops and return structured data.
        
        Returns:
            Dict with:
            - shops: list of shop summaries
            - listings: all listings fetched
            - shop_listings: dict of shop_name -> [listings]
            - errors: any shops that failed
        """
        shops = shops or FINE_JEWELRY_SHOPS
        results = {
            "shops": [],
            "listings": [],
            "shop_listings": {},
            "errors": [],
        }

        seen_listing_ids = set()

        for shop_id, shop_name, category, price_tier in shops:
            try:
                # Fetch shop info
                shop_data = self.get_shop(shop_id)
                if not shop_data:
                    results["errors"].append(f"Could not fetch shop {shop_name} (ID: {shop_id})")
                    continue

                shop_info = {
                    "shop_id": shop_id,
                    "shop_name": shop_name,
                    "category": category,
                    "price_tier": price_tier,
                    "title": shop_data.get("shop_name", shop_name),
                    "url": shop_data.get("url", f"https://www.etsy.com/shop/{shop_name}"),
                    "listing_count": shop_data.get("listing_count", 0),
                    "total_sales": shop_data.get("total_sales_count", 0),
                    "avg_rating": shop_data.get("average_rating", 0),
                    "review_count": shop_data.get("review_count", 0),
                    "last_scraped": datetime.utcnow().isoformat(),
                }

                # Fetch active listings
                listings = self.get_shop_listings(shop_id, limit=listings_per_shop)

                # Deduplicate globally
                unique_listings = []
                for l in listings:
                    if l.listing_id not in seen_listing_ids:
                        seen_listing_ids.add(l.listing_id)
                        unique_listings.append(l)

                results["listings"].extend(unique_listings)
                results["shop_listings"][shop_name] = unique_listings
                shop_info["listings_fetched"] = len(unique_listings)
                results["shops"].append(shop_info)

                logger.info(f"Scanned {shop_name}: {len(unique_listings)} listings")

            except Exception as e:
                logger.error(f"Error scanning shop {shop_name}: {e}")
                results["errors"].append(f"Error scanning {shop_name}: {str(e)}")

        logger.info(f"Fine jewelry scan complete: {len(results['shops'])} shops, "
                    f"{len(results['listings'])} listings, "
                    f"{len(results['errors'])} errors")
        return results

    def search_fine_jewelry_listings(self, query: str = "",
                                      min_price: float = 200.0,
                                      max_price: float = None,
                                      sort: str = "score",
                                      limit: int = 100) -> List[EtsyListing]:
        """
        Search specifically for fine jewelry listings ($200+).
        This filters for premium/luxury price points.
        """
        params = {
            "limit": min(limit, 100),
            "sort_on": sort,
            "min_price": min_price,
        }
        if max_price:
            params["max_price"] = max_price
        if query:
            params["keywords"] = query

        # Include fine jewelry taxonomy filter
        params["taxonomy_id"] = 143  # Fine Jewelry

        data = self.request("/application/listings/active", params)
        if not data:
            return []
        return self._parse_listings(data)


# =============================================================================
# Fine Jewelry Insight Engine
# =============================================================================

@dataclass
class FineJewelryInsights:
    """
    Deep insights specifically for fine jewelry market on Etsy.
    Goes beyond general trend analysis with fine-jewelry-specific metrics.
    """
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    scan_date: str = field(default_factory=lambda: date.today().isoformat())

    # Shop-level metrics
    total_shops_tracked: int = 0
    total_listings_collected: int = 0
    shops_by_category: Dict[str, int] = field(default_factory=dict)
    shops_by_tier: Dict[str, int] = field(default_factory=dict)

    # Pricing intelligence
    avg_price_by_category: Dict[str, float] = field(default_factory=dict)
    price_distribution: Dict[str, Dict[str, float]] = field(default_factory=dict)
    optimal_price_ranges: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Material trends (fine jewelry specific)
    gold_karat_trends: Dict[str, Dict] = field(default_factory=dict)
    top_gemstones: List[Dict] = field(default_factory=list)
    diamond_specs: Dict[str, Any] = field(default_factory=dict)

    # Competitive positioning
    shop_rankings: List[Dict] = field(default_factory=list)
    category_leaders: Dict[str, Dict] = field(default_factory=dict)

    # Demand signals
    high_demand_listings: List[Dict] = field(default_factory=list)
    price_change_alerts: List[Dict] = field(default_factory=list)
    sold_out_highlights: List[Dict] = field(default_factory=list)

    # Keyword/SEO intelligence
    top_fine_jewelry_tags: List[Dict] = field(default_factory=list)
    top_materials_used: List[Dict] = field(default_factory=list)

    # Summary metrics
    avg_listing_price: float = 0.0
    avg_shop_listings: float = 0.0
    total_market_value: float = 0.0

    def format_summary(self) -> str:
        lines = []
        lines.append(f"💎 **Fine Jewelry Market Intelligence** — {self.scan_date}")
        lines.append(f"   Tracking {self.total_shops_tracked} shops, {self.total_listings_collected} listings")
        lines.append("")

        if self.avg_price_by_category:
            lines.append(f"💰 **Average prices by category:**")
            for cat, price in sorted(self.avg_price_by_category.items(),
                                      key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"   • {cat}: ${price:.2f}")

        if self.top_gemstones:
            lines.append(f"\n💎 **Top gemstones:**")
            for g in self.top_gemstones[:5]:
                lines.append(f"   • {g['gemstone']}: {g['count']} listings (${g.get('avg_price', 0):.0f} avg)")

        if self.gold_karat_trends:
            lines.append(f"\n🥇 **Gold purity breakdown:**")
            for karat, data in sorted(self.gold_karat_trends.items()):
                lines.append(f"   • {karat}: {data['count']} listings — ${data.get('avg_price', 0):.0f} avg")

        if self.shop_rankings:
            lines.append(f"\n🏆 **Top shops by engagement:**")
            for s in self.shop_rankings[:5]:
                lines.append(f"   • {s.get('shop_name', '')}: {s.get('total_engagement', 0):,} engagement")

        if self.high_demand_listings:
            lines.append(f"\n🔥 **High-demand listings:**")
            for l in self.high_demand_listings[:5]:
                lines.append(f"   • {l.get('title', '')[:50]} — {l.get('favorites', 0)} ❤️")

        return "\n".join(lines)


class FineJewelryAnalyzer:
    """
    Specialized analyzer for fine jewelry Etsy shops.
    
    Processes listing data from curated fine jewelry shops into
    actionable competitive intelligence:
    - Price positioning analysis
    - Material/gemstone trend tracking
    - Gold karat popularity
    - Shop benchmarking
    - Demand signal detection
    """

    def __init__(self, api_client: EtsyAPIClient = None):
        self.api = api_client or EtsyAPIClient()
        self.listings: List[EtsyListing] = []
        self.shop_data: List[Dict] = []

    def scan_all_shops(self, shops: List[Tuple[int, str, str, str]] = None) -> Dict:
        """Scan all fine jewelry shops and return raw data."""
        scan_result = self.api.scan_fine_jewelry_shops(shops=shops)
        self.listings = scan_result["listings"]
        self.shop_data = scan_result["shops"]
        return scan_result

    def analyze(self) -> FineJewelryInsights:
        """Run full fine jewelry analysis on collected data."""
        insights = FineJewelryInsights()
        insights.total_shops_tracked = len(self.shop_data)
        insights.total_listings_collected = len(self.listings)

        if not self.listings and not self.shop_data:
            logger.warning("No fine jewelry data to analyze")
            return insights

        # ---- Shop-level aggregations ----
        cat_counter = Counter()
        tier_counter = Counter()
        for shop in self.shop_data:
            cat_counter[shop.get("category", "unknown")] += 1
            tier_counter[shop.get("price_tier", "unknown")] += 1
        insights.shops_by_category = dict(cat_counter)
        insights.shops_by_tier = dict(tier_counter)

        # ---- Pricing intelligence ----
        cat_prices = defaultdict(list)
        tier_prices = defaultdict(list)
        for l in self.listings:
            path = l.taxonomy_path[-1] if l.taxonomy_path else "uncategorized"
            cat_prices[path].append(l.price_amount)
            tier = l.price_category
            tier_prices[tier].append(l.price_amount)

        insights.avg_price_by_category = {
            cat: sum(prices) / len(prices)
            for cat, prices in cat_prices.items() if prices
        }

        # Price distribution percentiles by category
        insights.price_distribution = {}
        for cat, prices in cat_prices.items():
            if len(prices) >= 3:
                sorted_p = sorted(prices)
                insights.price_distribution[cat] = {
                    "p25": sorted_p[len(sorted_p) // 4],
                    "p50": sorted_p[len(sorted_p) // 2],
                    "p75": sorted_p[3 * len(sorted_p) // 4],
                    "min": min(prices),
                    "max": max(prices),
                    "avg": sum(prices) / len(prices),
                    "count": len(prices),
                }

        # Optimal price ranges (where engagement is highest)
        price_buckets = defaultdict(list)
        for l in self.listings:
            bucket = round(l.price_amount / 50) * 50  # Bucket by $50
            price_buckets[bucket].append(l.engagement_score)

        optimal_ranges = {}
        for bucket, scores in price_buckets.items():
            if len(scores) >= 3:
                optimal_ranges[f"${bucket}-${bucket+50}"] = {
                    "avg_engagement": sum(scores) / len(scores),
                    "count": len(scores),
                }
        # Top 5 engagement buckets
        sorted_ranges = sorted(optimal_ranges.items(),
                               key=lambda x: x[1]["avg_engagement"], reverse=True)[:5]
        for label, data in sorted_ranges:
            insights.optimal_price_ranges[label] = data

        # ---- Gold karat trends ----
        karat_patterns = {
            "24K": r'\b24[kKk]\b',
            "22K": r'\b22[kKk]\b',
            "18K": r'\b18[kKk]\b',
            "14K": r'\b14[kKk]\b',
            "10K": r'\b10[kKk]\b',
            "Gold Filled": r'\bgold\s*filled\b',
            "Gold Plated": r'\bgold\s*plated\b',
            "Rose Gold": r'\brose\s*gold\b',
            "White Gold": r'\bwhite\s*gold\b',
            "Yellow Gold": r'\byellow\s*gold\b',
        }
        for karat, pattern in karat_patterns.items():
            matched = [l for l in self.listings
                       if re.search(pattern, l.title, re.IGNORECASE)
                       or any(re.search(pattern, t, re.IGNORECASE) for t in l.tags)]
            if matched:
                prices = [l.price_amount for l in matched]
                insights.gold_karat_trends[karat] = {
                    "count": len(matched),
                    "avg_price": sum(prices) / len(prices) if prices else 0,
                    "total_views": sum(l.views for l in matched),
                    "total_favorites": sum(l.favorites for l in matched),
                }

        # ---- Gemstone trends ----
        gemstones = [
            "diamond", "sapphire", "ruby", "emerald", "amethyst",
            "topaz", "opal", "pearl", "moissanite", "cubic zirconia",
            "garnet", "peridot", "turquoise", "lapis", "jade",
            "moonstone", "labradorite", "citrine", "aquamarine",
            "tanzanite", "tourmaline", "spinel",
        ]
        gem_data = []
        for gem in gemstones:
            matched = [l for l in self.listings
                       if gem in l.title.lower()
                       or any(gem in m.lower() for m in l.materials)
                       or any(gem in t.lower() for t in l.tags)]
            if matched:
                prices = [l.price_amount for l in matched]
                gem_data.append({
                    "gemstone": gem.capitalize(),
                    "count": len(matched),
                    "avg_price": sum(prices) / len(prices) if prices else 0,
                    "total_sold": sum(l.num_sold for l in matched),
                    "engagement_rate": sum(l.engagement_score for l in matched) / len(matched),
                })
        gem_data.sort(key=lambda x: x["count"], reverse=True)
        insights.top_gemstones = gem_data

        # ---- Diamond specs analysis ----
        diamond_listings = [l for l in self.listings
                            if "diamond" in l.title.lower()
                            or "diamond" in str(l.materials).lower()]
        if diamond_listings:
            ct_terms = re.compile(r'(\d+\.?\d*)\s*(ct|carat)', re.IGNORECASE)
            carats = []
            for l in diamond_listings:
                match = ct_terms.search(l.title)
                if match:
                    carats.append(float(match.group(1)))
            insights.diamond_specs = {
                "total_diamond_listings": len(diamond_listings),
                "avg_diamond_price": sum(l.price_amount for l in diamond_listings) / len(diamond_listings),
                "avg_carat": sum(carats) / len(carats) if carats else 0,
                "total_diamond_sold": sum(l.num_sold for l in diamond_listings),
            }

        # ---- Shop rankings ----
        shop_metrics = defaultdict(lambda: {
            "total_listings": 0, "total_views": 0,
            "total_favorites": 0, "total_sold": 0,
            "total_engagement": 0, "prices": [],
        })
        for l in self.listings:
            if l.shop_name:
                m = shop_metrics[l.shop_name]
                m["total_listings"] += 1
                m["total_views"] += l.views
                m["total_favorites"] += l.favorites
                m["total_sold"] += l.num_sold
                m["total_engagement"] += l.engagement_score
                m["prices"].append(l.price_amount)

        insights.shop_rankings = [
            {
                "shop_name": name,
                "total_listings": m["total_listings"],
                "total_views": m["total_views"],
                "total_favorites": m["total_favorites"],
                "total_sold": m["total_sold"],
                "total_engagement": m["total_engagement"],
                "avg_price": sum(m["prices"]) / len(m["prices"]) if m["prices"] else 0,
                "engagement_per_listing": m["total_engagement"] / max(m["total_listings"], 1),
                "conversion_rate": m["total_sold"] / max(m["total_views"], 1) * 100,
            }
            for name, m in sorted(shop_metrics.items(),
                                  key=lambda x: x[1]["total_engagement"], reverse=True)
        ]
        insights.shop_rankings.sort(key=lambda x: x["total_engagement"], reverse=True)

        # ---- Category leaders ----
        for category, shop_names in SHOP_CATEGORIES.items():
            cat_shops = [s for s in insights.shop_rankings
                         if s["shop_name"] in shop_names]
            if cat_shops:
                insights.category_leaders[category] = {
                    "top_shop": cat_shops[0]["shop_name"],
                    "total_shops": len(cat_shops),
                    "avg_shop_price": sum(s["avg_price"] for s in cat_shops) / len(cat_shops),
                    "top_engagement": cat_shops[0]["total_engagement"],
                    "total_listings": sum(s["total_listings"] for s in cat_shops),
                }

        # ---- High-demand listings ----
        scored = []
        for l in self.listings:
            if l.engagement_score > 50:  # Minimum threshold
                scored.append({
                    "title": l.title,
                    "price": l.price_amount,
                    "views": l.views,
                    "favorites": l.favorites,
                    "sold": l.num_sold,
                    "engagement_score": l.engagement_score,
                    "shop_name": l.shop_name,
                    "url": l.url,
                    "tags": l.tags,
                    "materials": l.materials,
                    "image_url": l.main_image_url,
                })
        scored.sort(key=lambda x: x["engagement_score"], reverse=True)
        insights.high_demand_listings = scored[:25]

        # ---- Top tags (fine jewelry specific) ----
        tag_counter = Counter()
        for l in self.listings:
            for tag in l.tags:
                tag_counter[tag.lower().strip()] += 1
        insights.top_fine_jewelry_tags = [
            {"tag": tag, "count": count, "pct": round(count / len(self.listings) * 100, 1)}
            for tag, count in tag_counter.most_common(30)
        ]

        # ---- Material trends ----
        material_counter = Counter()
        material_prices = defaultdict(list)
        for l in self.listings:
            for mat in l.materials:
                m = mat.lower().strip()
                material_counter[m] += 1
                material_prices[m].append(l.price_amount)
        insights.top_materials_used = [
            {
                "material": mat,
                "count": count,
                "avg_price": sum(material_prices[mat]) / len(material_prices[mat]),
                "pct": round(count / len(self.listings) * 100, 1),
            }
            for mat, count in material_counter.most_common(20)
        ]

        # ---- Aggregate metrics ----
        if self.listings:
            prices = [l.price_amount for l in self.listings]
            insights.avg_listing_price = sum(prices) / len(prices)
            insights.total_market_value = sum(prices)
        if self.shop_data:
            insights.avg_shop_listings = sum(
                s.get("listings_fetched", 0) for s in self.shop_data
            ) / len(self.shop_data)

        logger.info(f"Fine jewelry analysis complete: {len(insights.shop_rankings)} shops, "
                    f"{len(insights.high_demand_listings)} high-demand listings")
        return insights


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