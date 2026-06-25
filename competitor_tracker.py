# =============================================================================
# JewelScope Research — Competitor Etsy Listing Tracker
# =============================================================================
#
# Fetches Etsy competitor listings, downloads images locally,
# and stores everything in SQLite for the UI to browse.
#
# Shows: listing photo, title, price, tags/keywords, shop name
# All stored locally — no external API needed for viewing.
# =============================================================================

import os
import re
import json
import hashlib
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Local image storage
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "static", "competitor_images")
os.makedirs(IMAGES_DIR, exist_ok=True)

# Default search queries for competitor discovery
COMPETITOR_SEARCHES = [
    "gold ring", "diamond ring", "engagement ring", "gold necklace",
    "silver necklace", "diamond earrings", "gold bracelet",
    "tennis bracelet", "pearl necklace", "gemstone ring",
    "moissanite ring", "wedding band", "gold chain",
    "hoop earrings", "stud earrings", "custom jewelry",
]


def _download_image(image_url: str, listing_id: int) -> Optional[str]:
    """
    Download a listing image to local storage.
    
    Returns:
        Local file path, or None if download failed.
    """
    if not image_url:
        return None

    try:
        # Determine file extension from URL
        parsed = urlparse(image_url)
        ext = os.path.splitext(parsed.path)[1] or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            ext = ".jpg"

        filename = f"etsy_{listing_id}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)

        # Skip if already downloaded
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return filepath

        resp = httpx.get(image_url, timeout=15, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(filepath, "wb") as f:
                f.write(resp.content)
            logger.info(f"Downloaded image: {filename} ({len(resp.content)} bytes)")
            return filepath
        else:
            logger.warning(f"Failed to download {image_url}: HTTP {resp.status_code}")
            return None

    except Exception as e:
        logger.warning(f"Image download error for listing {listing_id}: {e}")
        return None


class CompetitorTracker:
    """
    Fetches Etsy competitor listings, downloads images,
    and stores them in the local database.
    
    Uses EtsyAPIClient when API key is available.
    Falls back to displaying any existing local data.
    """

    def __init__(self, db_path: str = ""):
        from database import DatabaseManager
        self.db_path = db_path
        self.db = None
        self.stats = {"searches_run": 0, "listings_found": 0, "images_downloaded": 0}

    def _get_db(self):
        if self.db is None:
            from database import DatabaseManager
            db_path = self.db_path or os.path.join(
                os.path.dirname(__file__), "databases", "jewelscope.db"
            )
            self.db = DatabaseManager(db_path)
        return self.db

    def scan_competitors(self, searches: List[str] = None,
                         listings_per_search: int = 20,
                         download_images: bool = True) -> Dict[str, Any]:
        """
        Search Etsy for competitor jewelry listings and store locally.
        
        Uses the Etsy API if available. Gracefully reports if not.
        
        Args:
            searches: List of search queries (uses defaults if None)
            listings_per_search: Max listings per query
            download_images: Whether to download listing images locally
            
        Returns:
            Dict with scan results
        """
        searches = searches or COMPETITOR_SEARCHES

        # Try to use Etsy API
        try:
            from etsy_api import EtsyAPIClient, FineJewelryAnalyzer
            api_key = os.environ.get("ETSY_API_KEY", "")
            if api_key:
                client = EtsyAPIClient(api_key)
                analyzer = FineJewelryAnalyzer(client)

                all_listings = []
                for query in searches:
                    try:
                        listings = client.search_jewelry_listings(
                            query=query, limit=listings_per_search
                        )
                        for l in listings:
                            listing_dict = l.to_dict()
                            listing_dict["search_query"] = query
                            all_listings.append(listing_dict)
                        self.stats["searches_run"] += 1
                    except Exception as e:
                        logger.warning(f"Search '{query}' failed: {e}")

                self.stats["listings_found"] = len(all_listings)

                # Download images locally
                if download_images and all_listings:
                    for listing in all_listings:
                        img_url = listing.get("main_image_url", "")
                        if img_url:
                            local_path = _download_image(img_url, listing["listing_id"])
                            if local_path:
                                listing["local_image_path"] = local_path
                                self.stats["images_downloaded"] += 1

                # Save to database
                db = self._get_db()
                saved = db.save_competitor_listings(all_listings)

                logger.info(f"Competitor scan: {saved} listings saved, "
                            f"{self.stats['images_downloaded']} images downloaded")
                return {
                    "success": True,
                    "searches_run": self.stats["searches_run"],
                    "listings_found": self.stats["listings_found"],
                    "listings_saved": saved,
                    "images_downloaded": self.stats["images_downloaded"],
                    "source": "etsy_api",
                }

        except ImportError as e:
            logger.warning(f"Etsy API not available: {e}")

        except Exception as e:
            logger.warning(f"Competitor scan error: {e}")

        # If we get here, Etsy API wasn't available
        return {
            "success": False,
            "searches_run": 0,
            "listings_found": 0,
            "listings_saved": 0,
            "images_downloaded": 0,
            "source": None,
            "error": "Etsy API key not configured — set ETSY_API_KEY env var",
        }

    def get_listings(self, limit: int = 100, offset: int = 0,
                     shop_name: str = None, search_query: str = None,
                     sort_by: str = "scraped_at") -> List[Dict]:
        """Get competitor listings from local database."""
        db = self._get_db()
        records = db.get_competitor_listings(
            limit=limit, offset=offset,
            shop_name=shop_name, search_query=search_query,
            sort_by=sort_by,
        )
        return [r.to_dict() for r in records]

    def get_stats(self) -> Dict:
        """Get aggregate stats about stored competitor data."""
        db = self._get_db()
        return db.get_competitor_stats()

    def get_image_url(self, listing_id: int) -> Optional[str]:
        """
        Get the local URL path for a listing image.
        Returns a path that Streamlit can serve.
        """
        local_path = os.path.join(IMAGES_DIR, f"etsy_{listing_id}.jpg")
        if os.path.exists(local_path):
            return local_path
        # Try other extensions
        for ext in [".jpeg", ".png", ".gif", ".webp"]:
            path = os.path.join(IMAGES_DIR, f"etsy_{listing_id}{ext}")
            if os.path.exists(path):
                return path
        return None

    def delete_listing(self, listing_id: int) -> bool:
        """Delete a competitor listing and its local image."""
        db = self._get_db()
        with db.get_session() as session:
            from database import CompetitorListing
            record = session.query(CompetitorListing).filter_by(
                listing_id=listing_id
            ).first()
            if record:
                # Delete local image
                if record.local_image_path and os.path.exists(record.local_image_path):
                    os.remove(record.local_image_path)
                session.delete(record)
                session.commit()
                return True
        return False


# =============================================================================
# Standalone usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    tracker = CompetitorTracker()
    print("Competitor Tracker — JewelScope Research")
    print("=" * 50)

    # Show local stats
    stats = tracker.get_stats()
    print(f"\nLocal database: {stats['total_listings']} listings, "
          f"{stats['unique_shops']} shops, avg ${stats['avg_price']}")

    if stats["recent_queries"]:
        print(f"Recent searches: {', '.join(stats['recent_queries'][:5])}")

    print("\nTo scan competitors, set ETSY_API_KEY and run:")
    print("  tracker.scan_competitors()")
    print(f"Images stored in: {IMAGES_DIR}")