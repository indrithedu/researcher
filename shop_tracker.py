# =============================================================================
# JewelScope Research — Etsy Competitive Shop Tracker
# =============================================================================
#
# Tracks specific Etsy jewelry shops and monitors:
#   - New listings (what competitors are launching)
#   - Price changes (pricing strategy shifts)
#   - Sold items (demand signals)
#   - Listing title/tag changes (SEO strategy)
#
# Uses Etsy API with user-provided API key.
# Stores historical snapshots in SQLite for change detection.
# =============================================================================

import json
import logging
import time
import hashlib
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class TrackedShop:
    """An Etsy shop being tracked."""
    shop_id: int
    shop_name: str
    shop_url: str = ""
    added_date: str = ""
    last_scraped: str = ""
    total_listings: int = 0
    active_listings: int = 0
    total_sales: int = 0
    avg_price: float = 0.0
    materials_used: List[str] = field(default_factory=list)
    categories_sold: List[str] = field(default_factory=list)
    listing_count_history: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ListingSnapshot:
    """A snapshot of a listing at a point in time."""
    listing_id: int
    shop_id: int
    title: str
    price: float
    description_hash: str
    tags: List[str]
    materials: List[str]
    quantity: int
    state: str
    snapshot_date: str
    was_sold: bool = False
    previous_price: float = 0.0
    price_change_pct: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ShopAlert:
    """An alert about a shop change."""
    alert_type: str  # new_listing, price_change, sold_out, title_change, tag_change
    shop_name: str
    listing_title: str
    listing_url: str = ""
    old_value: str = ""
    new_value: str = ""
    detected_at: str = ""
    severity: str = "info"  # info, warning, important

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ShopTrackerReport:
    """Complete competitive intelligence report."""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    shops_tracked: int = 0
    total_listings: int = 0

    # Alerts since last check
    new_alerts: List[Dict] = field(default_factory=list)

    # New listings found
    new_listings: List[Dict] = field(default_factory=list)

    # Price changes detected
    price_changes: List[Dict] = field(default_factory=list)

    # Recently sold out
    sold_out: List[Dict] = field(default_factory=list)

    # Shop metrics overview
    shop_overview: List[Dict] = field(default_factory=list)

    # Tag/material changes
    strategy_changes: List[Dict] = field(default_factory=list)

    def format_summary(self) -> str:
        lines = []
        lines.append(f"👀 **Competitive Shop Tracker** — {self.generated_at[:10]}")
        lines.append(f"   Tracking {self.shops_tracked} shops, {self.total_listings} listings")
        lines.append("")

        if self.new_listings:
            lines.append("🆕 **New Listings:**")
            for n in self.new_listings[:5]:
                lines.append(f"   🆕 {n.get('title', '')[:60]} — ${n.get('price', 0):.2f}")

        if self.price_changes:
            lines.append("\n💰 **Price Changes:**")
            for p in self.price_changes[:5]:
                icon = "📈" if p.get('price_change', 0) > 0 else "📉"
                lines.append(f"   {icon} {p.get('title', '')[:50]} — "
                             f"${p.get('old_price', 0):.2f} → ${p.get('new_price', 0):.2f}")

        if self.sold_out:
            lines.append("\n🚫 **Sold Out:**")
            for s in self.sold_out[:5]:
                lines.append(f"   🚫 {s.get('title', '')[:50]} — {s.get('shop_name', '')}")

        if self.new_alerts:
            lines.append(f"\n🔔 **{len(self.new_alerts)} alerts since last check**")

        return "\n".join(lines)


# =============================================================================
# Shop Tracker
# =============================================================================

class EtsyShopTracker:
    """
    Tracks Etsy jewelry shops for competitive intelligence.
    
    Features:
    - Monitor new listings from competitors
    - Detect price changes (increase/decrease)
    - Track sold-out items (demand signal)
    - Detect SEO changes (title/tag updates)
    - Historical snapshots for trend analysis
    - Configurable alert thresholds
    
    Requires ETSY_API_KEY environment variable.
    """

    # Default shops to track (high-profile jewelry shops on Etsy)
    # Users can add their own via config
    DEFAULT_SHOPS = [
        # These are example shop IDs — users replace with their competitors
        # Format: (shop_id, shop_name)
    ]

    def __init__(self, api_client=None, db_path: str = ""):
        self.api = api_client
        self.db_path = db_path

        # In-memory storage (for demo; SQLite in production)
        self.shops: Dict[int, TrackedShop] = {}
        self.history: Dict[str, List[ListingSnapshot]] = defaultdict(list)
        self.alert_history: List[ShopAlert] = []

        # Tracked shops config
        self.tracked_shops: List[Tuple[int, str]] = []

    def add_shop(self, shop_id: int, shop_name: str = ""):
        """Add a shop to track."""
        self.tracked_shops.append((shop_id, shop_name))
        logger.info(f"Added shop {shop_id} ({shop_name}) to tracking")

    def add_shops(self, shops: List[Tuple[int, str]]):
        """Add multiple shops at once."""
        for shop_id, name in shops:
            self.add_shop(shop_id, name)

    def remove_shop(self, shop_id: int):
        """Stop tracking a shop."""
        self.tracked_shops = [(sid, n) for sid, n in self.tracked_shops if sid != shop_id]
        logger.info(f"Removed shop {shop_id} from tracking")

    def scan_all(self) -> ShopTrackerReport:
        """Scan all tracked shops and detect changes."""
        report = ShopTrackerReport()
        report.shops_tracked = len(self.tracked_shops)

        if not self.api:
            logger.warning("No Etsy API client — shop tracker disabled")
            report.shops_tracked = 0
            return report

        all_listings = []
        all_alerts = []

        for shop_id, shop_name in self.tracked_shops:
            try:
                # Fetch shop info
                shop_data = self.api.get_shop(shop_id)
                if not shop_data:
                    logger.warning(f"Could not fetch shop {shop_id}")
                    continue

                shop_name = shop_name or shop_data.get("shop_name", f"shop_{shop_id}")

                # Fetch active listings
                listings = self.api.get_shop_listings(shop_id, limit=100)
                report.total_listings += len(listings)

                # Convert to snapshots and detect changes
                snapshots = []
                for listing in listings:
                    snap = self._create_snapshot(listing, shop_id)
                    snapshots.append(snap)
                    all_listings.append(snap)

                    # Detect changes against history
                    changes = self._detect_changes(snap)
                    all_alerts.extend(changes)

                # Update shop record
                if shop_id not in self.shops:
                    self.shops[shop_id] = TrackedShop(
                        shop_id=shop_id,
                        shop_name=shop_name,
                        added_date=datetime.utcnow().isoformat(),
                    )

                shop = self.shops[shop_id]
                shop.last_scraped = datetime.utcnow().isoformat()
                shop.active_listings = len(listings)
                prices = [l.price_amount for l in listings]
                shop.avg_price = sum(prices) / len(prices) if prices else 0

                # Store snapshots in history
                for snap in snapshots:
                    key = f"{shop_id}:{snap.listing_id}"
                    self.history[key].append(snap)

                # Keep only last 10 snapshots per listing
                for key in self.history:
                    if len(self.history[key]) > 10:
                        self.history[key] = self.history[key][-10:]

                logger.info(f"Scanned {shop_name}: {len(listings)} listings, "
                           f"{len([a for a in all_alerts if a.alert_type == 'price_change'])} price changes")

            except Exception as e:
                logger.error(f"Error scanning shop {shop_id}: {e}")
                continue

        # Build report sections
        report.shop_overview = [s.to_dict() for s in self.shops.values()]

        # Categorize alerts
        for alert in all_alerts:
            d = alert.to_dict()
            report.new_alerts.append(d)

            if alert.alert_type == "new_listing":
                report.new_listings.append(d)
            elif alert.alert_type == "price_change":
                report.price_changes.append(d)
            elif alert.alert_type == "sold_out":
                report.sold_out.append(d)
            elif alert.alert_type in ("title_change", "tag_change"):
                report.strategy_changes.append(d)

        # Deduplicate
        report.new_listings = self._dedup(report.new_listings, "listing_title")
        report.price_changes = self._dedup(report.price_changes, "listing_title")

        self.alert_history.extend(all_alerts)

        return report

    def _create_snapshot(self, listing, shop_id: int) -> ListingSnapshot:
        """Create a snapshot from an EtsyListing object or dict."""
        if hasattr(listing, "to_dict"):
            d = listing.to_dict()
        else:
            d = listing if isinstance(listing, dict) else {}

        desc = d.get("description", "") or d.get("title", "")
        desc_hash = hashlib.md5(desc.encode()).hexdigest()[:16]

        return ListingSnapshot(
            listing_id=d.get("listing_id", 0),
            shop_id=shop_id,
            title=d.get("title", ""),
            price=float(d.get("price_amount", 0)),
            description_hash=desc_hash,
            tags=d.get("tags", []),
            materials=d.get("materials", []),
            quantity=d.get("quantity", 0),
            state=d.get("state", "active"),
            snapshot_date=datetime.utcnow().isoformat(),
            was_sold=d.get("state") == "sold_out" or d.get("quantity", 0) == 0,
        )

    def _detect_changes(self, snapshot: ListingSnapshot) -> List[ShopAlert]:
        """Detect changes compared to previous snapshot."""
        alerts = []
        key = f"{snapshot.shop_id}:{snapshot.listing_id}"
        history = self.history.get(key, [])

        if not history:
            # First time seeing this listing — it's new
            shop_name = self.shops.get(snapshot.shop_id, TrackedShop(0, "")).shop_name
            alerts.append(ShopAlert(
                alert_type="new_listing",
                shop_name=shop_name or f"shop_{snapshot.shop_id}",
                listing_title=snapshot.title,
                severity="info" if snapshot.price < 100 else "important",
                detected_at=snapshot.snapshot_date,
            ))
            return alerts

        # Compare with latest snapshot
        prev = history[-1]

        # Price change
        if abs(snapshot.price - prev.price) > 0.01 and prev.price > 0:
            change_pct = ((snapshot.price - prev.price) / prev.price) * 100
            if abs(change_pct) >= 5:  # Only alert on >= 5% change
                shop_name = self.shops.get(snapshot.shop_id, TrackedShop(0, "")).shop_name
                alerts.append(ShopAlert(
                    alert_type="price_change",
                    shop_name=shop_name or f"shop_{snapshot.shop_id}",
                    listing_title=snapshot.title,
                    old_value=f"${prev.price:.2f}",
                    new_value=f"${snapshot.price:.2f}",
                    severity="important" if abs(change_pct) > 20 else "warning",
                    detected_at=snapshot.snapshot_date,
                ))

        # Sold out
        if snapshot.was_sold and not prev.was_sold:
            shop_name = self.shops.get(snapshot.shop_id, TrackedShop(0, "")).shop_name
            alerts.append(ShopAlert(
                alert_type="sold_out",
                shop_name=shop_name or f"shop_{snapshot.shop_id}",
                listing_title=snapshot.title,
                severity="important",
                detected_at=snapshot.snapshot_date,
            ))

        # Title change (SEO strategy)
        if snapshot.title != prev.title:
            shop_name = self.shops.get(snapshot.shop_id, TrackedShop(0, "")).shop_name
            alerts.append(ShopAlert(
                alert_type="title_change",
                shop_name=shop_name or f"shop_{snapshot.shop_id}",
                listing_title=snapshot.title,
                old_value=prev.title[:80],
                new_value=snapshot.title[:80],
                severity="info",
                detected_at=snapshot.snapshot_date,
            ))

        # Tag change (SEO strategy)
        if set(snapshot.tags) != set(prev.tags) and snapshot.tags and prev.tags:
            old_set = set(prev.tags)
            new_set = set(snapshot.tags)
            added = new_set - old_set
            removed = old_set - new_set
            if added or removed:
                shop_name = self.shops.get(snapshot.shop_id, TrackedShop(0, "")).shop_name
                alerts.append(ShopAlert(
                    alert_type="tag_change",
                    shop_name=shop_name or f"shop_{snapshot.shop_id}",
                    listing_title=snapshot.title,
                    old_value=f"Removed: {', '.join(list(removed)[:3])}" if removed else "",
                    new_value=f"Added: {', '.join(list(added)[:3])}" if added else "",
                    severity="info",
                    detected_at=snapshot.snapshot_date,
                ))

        return alerts

    def _dedup(self, items: List[Dict], key: str) -> List[Dict]:
        """Deduplicate list of dicts by a key."""
        seen = set()
        result = []
        for item in items:
            val = item.get(key, "")
            if val not in seen:
                seen.add(val)
                result.append(item)
        return result

    def get_shop_report(self, shop_id: int) -> Optional[Dict]:
        """Get detailed report for a single shop."""
        if shop_id not in self.shops:
            return None

        shop = self.shops[shop_id]
        shop_listings = []
        for key, snaps in self.history.items():
            sid = int(key.split(":")[0])
            if sid == shop_id:
                current = snaps[-1] if snaps else None
                if current:
                    shop_listings.append(current.to_dict())

        return {
            "shop": shop.to_dict(),
            "current_listings": shop_listings[:50],
            "alert_count": len([a for a in self.alert_history if a.shop_name == shop.shop_name]),
        }


# =============================================================================
# Quick test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Etsy Competitive Shop Tracker — JewelScope Research")
    print("=" * 60)

    tracker = EtsyShopTracker()

    # Add some demo tracked shops
    tracker.add_shop(12345678, "Example Jewelry Shop")
    tracker.add_shop(87654321, "Diamond Boutique")

    # Create demo snapshots for testing change detection
    from etsy_api import EtsyAPIClient
    key = __import__('os').environ.get("ETSY_API_KEY", "")
    if key:
        from etsy_api import EtsyAPIClient
        tracker.api = EtsyAPIClient(key)
        print("\nScanning tracked shops...")
        report = tracker.scan_all()
        print(report.format_summary())
    else:
        print("\n⚠️  No ETSY_API_KEY configured.")
        print("   Set it to scan real shops: export ETSY_API_KEY='your_key'")
        print("\nDemo mode: showing sample shop tracker output...\n")

        # Demo report
        report = ShopTrackerReport()
        report.shops_tracked = 3
        report.total_listings = 147
        report.new_listings = [
            {"title": "Handcrafted Gold Solitaire Ring - 18k Yellow Gold",
             "price": 485.00, "shop_name": "Luxury Jewelry Co."},
            {"title": "Diamond Tennis Bracelet - Lab Grown VS1",
             "price": 1250.00, "shop_name": "Diamond Boutique"},
            {"title": "Sterling Silver Hoop Earrings - Hammered Finish",
             "price": 68.00, "shop_name": "Silver & Stone"},
        ]
        report.price_changes = [
            {"title": "Vintage Pearl Necklace - 16 inch",
             "old_price": 245.00, "new_price": 295.00, "price_change": 50.0,
             "shop_name": "Vintage Luxe"},
            {"title": "Gold Chain Bracelet - 14k",
             "old_price": 180.00, "new_price": 162.00, "price_change": -18.0,
             "shop_name": "Gold Standard"},
        ]
        report.sold_out = [
            {"title": "Rose Gold Engagement Ring - Oval Cut", "shop_name": "Diamond Boutique"},
            {"title": "Custom Name Necklace - Gold Filled", "shop_name": "Personalized Gifts"},
        ]
        report.new_alerts = [
            {"alert_type": "new_listing", "listing_title": "New: Gold Ring",
             "shop_name": "Shop A", "severity": "info"},
            {"alert_type": "price_change", "listing_title": "Price Drop: Silver Necklace",
             "shop_name": "Shop B", "severity": "warning"},
        ]

        print(report.format_summary())
        print("\n✅ Shop tracker ready. Add competitors' shop IDs to track real data.")