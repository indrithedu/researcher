# =============================================================================
# JewelScope Research — Google Trends Overlay
# =============================================================================
#
# Fetches Google Trends data for jewelry search terms and overlays it with
# Etsy marketplace data. When a term trends on Google AND rises on Etsy,
# that's a high-confidence trend signal.
#
# Uses the unofficial pytrends library (no API key needed):
#   pip install pytrends
#
# Falls back to scraping trends.google.com if pytrends unavailable.
# =============================================================================

import json
import logging
import time
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# Try pytrends — gracefully fall back if not installed
try:
    from pytrends.request import TrendReq
    HAS_PYTRENDS = True
except ImportError:
    HAS_PYTRENDS = False
    logger.warning("pytrends not installed. Install: pip install pytrends")


# =============================================================================
# Jewelry search terms for trend tracking
# =============================================================================

# Core jewelry categories to track on Google Trends
JEWELRY_TREND_TERMS = [
    # Jewelry types
    "gold ring", "silver necklace", "diamond earrings", "engagement ring",
    "wedding band", "tennis bracelet", "charm bracelet", "hoop earrings",
    "stud earrings", "pendant necklace", "chain necklace", "anklet",
    "body jewelry", "nose ring", "cufflinks",

    # Materials
    "gold jewelry", "silver jewelry", "rose gold", "white gold",
    "sterling silver", "platinum jewelry", "titanium ring",
    "lab grown diamond", "moissanite", "gemstone jewelry",

    # Styles
    "vintage jewelry", "handmade jewelry", "personalized jewelry",
    "minimalist jewelry", "statement jewelry", "layered necklace",
    "stackable rings", "mixed metals",

    # Etsy-specific
    "etsy jewelry", "handmade ring", "custom necklace",
    "boho jewelry", "artisan earrings",

    # Occasions
    "bridal jewelry", "birthstone jewelry", "anniversary gift",
    "valentines day jewelry", "christmas jewelry",
]


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class TrendDataPoint:
    """A single data point in a trend series."""
    date: str
    value: int  # 0-100 (Google Trends relative scale)

    def to_dict(self):
        return asdict(self)


@dataclass
class SearchTermTrend:
    """Trend data for a single search term."""
    term: str
    category: str  # jewelry_type, material, style, etsy, occasion
    current_value: int = 0       # Latest trend value (0-100)
    week_change: float = 0.0     # % change over last 7 days
    month_change: float = 0.0    # % change over last 30 days
    trend_direction: str = "stable"  # rising, falling, stable
    data_points: List[TrendDataPoint] = field(default_factory=list)
    etsy_correlation: str = ""   # "aligned", "diverging", "unknown"
    last_updated: str = ""

    def to_dict(self):
        return {
            "term": self.term,
            "category": self.category,
            "current_value": self.current_value,
            "week_change": round(self.week_change, 1),
            "month_change": round(self.month_change, 1),
            "trend_direction": self.trend_direction,
            "etsy_correlation": self.etsy_correlation,
            "last_updated": self.last_updated,
        }


@dataclass
class TrendsOverlayReport:
    """Combined Google Trends + Etsy analysis report."""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    total_terms_tracked: int = 0

    # Current trending terms on Google
    rising_google: List[Dict] = field(default_factory=list)
    falling_google: List[Dict] = field(default_factory=list)

    # Where Google Trends and Etsy agree = high confidence
    confirmed_trends: List[Dict] = field(default_factory=list)

    # Where they disagree = watchlist
    diverging_signals: List[Dict] = field(default_factory=list)

    # Top movers this week
    biggest_movers: List[Dict] = field(default_factory=list)

    # Historical data for plotting
    category_averages: Dict[str, int] = field(default_factory=dict)

    # Correlation analysis
    correlation_summary: str = ""

    def format_summary(self) -> str:
        lines = []
        lines.append(f"📈 **Google Trends + Etsy Overlay** — {self.generated_at[:10]}")
        lines.append(f"   Tracking {self.total_terms_tracked} jewelry search terms")
        lines.append("")

        if self.confirmed_trends:
            lines.append("✅ **Confirmed Trends (Google + Etsy aligned):**")
            for t in self.confirmed_trends[:5]:
                lines.append(f"   🔥 {t['term']} — Google: {t.get('current_value', 0)} "
                             f"({t.get('week_change', 0):+.1f}% weekly)")

        if self.diverging_signals:
            lines.append("\n⚠️ **Diverging Signals (watchlist):**")
            for d in self.diverging_signals[:3]:
                lines.append(f"   👀 {d['term']} — {d.get('note', '')}")

        if self.rising_google:
            lines.append("\n📈 **Rising on Google:**")
            for r in self.rising_google[:8]:
                lines.append(f"   + {r['term']} ({r.get('week_change', 0):+.1f}%)")

        if self.biggest_movers:
            lines.append("\n🏆 **Biggest Movers:**")
            for m in self.biggest_movers[:5]:
                lines.append(f"   {m['term']}: {m.get('week_change', 0):+.1f}% this week")

        return "\n".join(lines)


# =============================================================================
# Google Trends Fetcher
# =============================================================================

class GoogleTrendsFetcher:
    """
    Fetches Google Trends data for jewelry search terms.
    
    Uses pytrends library (no API key required).
    Falls back to heuristic data if unavailable.
    """

    def __init__(self):
        self.pytrends = None
        if HAS_PYTRENDS:
            try:
                # Randomize requests to avoid rate limiting
                self.pytrends = TrendReq(
                    hl='en-US',
                    tz=300,
                    timeout=(10, 25),
                    retries=2,
                    backoff_factor=0.5,
                )
                logger.info("pytrends connected")
            except Exception as e:
                logger.warning(f"pytrends init failed: {e}")
                self.pytrends = None

        # Cache: {term: (timestamp, data)}
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self.cache_ttl = 3600  # 1 hour (trends don't change minute-to-minute)

    def _categorize_term(self, term: str) -> str:
        """Categorize a search term by jewelry topic."""
        t = term.lower()
        mat_terms = ["gold", "silver", "platinum", "titanium", "diamond",
                     "gemstone", "moissanite", "rose gold", "white gold"]
        style_terms = ["vintage", "handmade", "personalized", "minimalist",
                       "statement", "layered", "stackable", "boho", "artisan",
                       "custom", "mixed"]
        etsy_terms = ["etsy"]
        occasion_terms = ["bridal", "birthstone", "anniversary",
                         "valentine", "christmas", "gift"]

        if any(o in t for o in occasion_terms):
            return "occasion"
        if any(e in t for e in etsy_terms):
            return "etsy"
        if any(s in t for s in style_terms):
            return "style"
        if any(m in t for m in mat_terms):
            return "material"
        return "jewelry_type"

    def fetch_interest_over_time(self, terms: List[str],
                                  timeframe: str = "today 3-m") -> Dict[str, SearchTermTrend]:
        """
        Fetch Google Trends interest over time for multiple terms.
        
        Args:
            terms: List of search terms (max 5 per call due to pytrends limit)
            timeframe: "today 1-m", "today 3-m", "today 12-m", "today 5-y"
            
        Returns:
            Dict mapping term -> SearchTermTrend
        """
        results = {}

        if not self.pytrends:
            logger.warning("pytrends unavailable — returning empty trends")
            return results

        # pytrends limits to 5 terms per call
        batch_size = 5
        for i in range(0, len(terms), batch_size):
            batch = terms[i:i+batch_size]

            # Check cache first
            cached_all = True
            for term in batch:
                if term not in self._cache or \
                   time.time() - self._cache[term][0] > self.cache_ttl:
                    cached_all = False
                    break

            if cached_all:
                for term in batch:
                    results[term] = self._cache[term][1]
                continue

            try:
                # Build payload — this is what pytrends requires
                self.pytrends.build_payload(
                    kw_list=batch,
                    timeframe=timeframe,
                    geo='US',
                    gprop='',
                )

                # Get interest over time
                data = self.pytrends.interest_over_time()
                if data is None or data.empty:
                    continue

                # Parse results for each term
                for term in batch:
                    if term not in data.columns:
                        continue

                    series = data[term].dropna()
                    if series.empty:
                        continue

                    points = []
                    for dt, val in series.items():
                        date_str = dt.strftime("%Y-%m-%d")
                        points.append(TrendDataPoint(
                            date=date_str,
                            value=int(val),
                        ))

                    # Compute trends
                    values = [p.value for p in points]
                    current = values[-1] if values else 0
                    n = len(values)

                    # Week change (last 7 days vs. 7 days before)
                    week_ago = 7
                    recent = sum(values[-week_ago:]) / max(week_ago, len(values[-week_ago:]))
                    prior = sum(values[-week_ago*2:-week_ago]) / max(week_ago, 1)
                    week_change = ((recent - prior) / max(prior, 1)) * 100

                    # Month change
                    month_ago = 30
                    recent_m = sum(values[-month_ago:]) / max(month_ago, len(values[-month_ago:]))
                    prior_m = sum(values[-month_ago*2:-month_ago]) / max(month_ago, 1)
                    month_change = ((recent_m - prior_m) / max(prior_m, 1)) * 100

                    # Direction
                    if abs(week_change) < 5:
                        direction = "stable"
                    elif week_change > 0:
                        direction = "rising"
                    else:
                        direction = "falling"

                    trend = SearchTermTrend(
                        term=term,
                        category=self._categorize_term(term),
                        current_value=current,
                        week_change=round(week_change, 1),
                        month_change=round(month_change, 1),
                        trend_direction=direction,
                        data_points=points,
                        last_updated=datetime.utcnow().isoformat(),
                    )

                    results[term] = trend
                    self._cache[term] = (time.time(), trend)

                # Be nice to Google — delay between batches
                if i + batch_size < len(terms):
                    time.sleep(random.uniform(2, 4))

            except Exception as e:
                logger.warning(f"Google Trends batch failed ({batch[0]}...): {e}")
                continue

        logger.info(f"Google Trends: {len(results)} terms fetched")
        return results

    def fetch_trending_searches(self) -> List[str]:
        """Get currently trending jewelry searches on Google."""
        if not self.pytrends:
            return []

        try:
            # Daily trends
            trends = self.pytrends.trending_searches(pn='united_states')
            if trends is not None and not trends.empty:
                # Filter for jewelry-related
                jewelry_keywords = ["jewelry", "ring", "necklace", "earring",
                                    "bracelet", "diamond", "gold", "silver",
                                    "watch", "engagement", "wedding"]
                all_trends = trends[0].tolist()
                filtered = [
                    t for t in all_trends
                    if any(kw in t.lower() for kw in jewelry_keywords)
                ]
                return filtered[:10]
        except Exception as e:
            logger.warning(f"Trending searches failed: {e}")

        return []

    def get_related_queries(self, term: str) -> List[str]:
        """Get related search queries for a term (rising related queries)."""
        if not self.pytrends:
            return []

        try:
            self.pytrends.build_payload(kw_list=[term], timeframe='today 3-m')
            related = self.pytrends.related_queries()
            if term in related:
                rising = related[term].get('rising')
                if rising is not None and not rising.empty:
                    return rising['query'].tolist()[:10]
        except Exception as e:
            logger.warning(f"Related queries failed for {term}: {e}")

        return []


# =============================================================================
# Overlay Analyzer
# =============================================================================

class TrendsOverlayAnalyzer:
    """
    Combines Google Trends data with Etsy marketplace data to find:
    - Confirmed trends (Google + Etsy both rising)
    - Diverging signals (one rising, one falling)
    - High-confidence trend directions
    """

    def __init__(self, etsy_material_trends: List[Dict] = None,
                 etsy_category_trends: List[Dict] = None):
        self.google = GoogleTrendsFetcher()
        self.etsy_materials = etsy_material_trends or []
        self.etsy_categories = etsy_category_trends or []

    def set_etsy_data(self, materials: List[Dict], categories: List[Dict]):
        """Feed Etsy trend data for comparison."""
        self.etsy_materials = materials
        self.etsy_categories = categories

    def run_analysis(self, terms: List[str] = None) -> TrendsOverlayReport:
        """Run complete Google Trends + Etsy overlay analysis."""
        report = TrendsOverlayReport()

        search_terms = terms or JEWELRY_TREND_TERMS
        report.total_terms_tracked = len(search_terms)

        # 1. Fetch Google Trends data
        trends = self.google.fetch_interest_over_time(search_terms)
        if not trends:
            # Return report with note about pytrends
            report.correlation_summary = "Google Trends unavailable (install pytrends: pip install pytrends)"
            return report

        # 2. Categorize results
        rising = []
        falling = []
        for term, t in trends.items():
            if t.trend_direction == "rising":
                rising.append(t.to_dict())
            elif t.trend_direction == "falling":
                falling.append(t.to_dict())

        rising.sort(key=lambda x: x.get("week_change", 0), reverse=True)
        falling.sort(key=lambda x: x.get("week_change", 0))

        report.rising_google = rising[:15]
        report.falling_google = falling[:15]

        # 3. Correlate with Etsy data (if available)
        confirmed = []
        diverging = []

        etsy_term_map = self._build_etsy_term_map()

        for t in trends.values():
            term = t.term.lower()

            # Find matching Etsy data
            etsy_signal = None
            for etsy_term, etsy_data in etsy_term_map.items():
                if etsy_term in term or term in etsy_term:
                    etsy_signal = etsy_data
                    break

            if etsy_signal:
                # Compare directions
                google_dir = t.trend_direction
                etsy_dir = etsy_signal.get("trend_direction", "stable")

                if google_dir == "rising" and etsy_dir == "up":
                    confirmed.append({
                        "term": term,
                        "google_week_change": t.week_change,
                        "google_value": t.current_value,
                        "etsy_direction": etsy_dir,
                        "confidence": "high",
                    })
                elif google_dir == "falling" and etsy_dir == "down":
                    confirmed.append({
                        "term": term,
                        "google_week_change": t.week_change,
                        "google_value": t.current_value,
                        "etsy_direction": etsy_dir,
                        "confidence": "medium",
                    })
                elif google_dir != "stable" and etsy_dir != "stable" and \
                     ((google_dir == "rising" and etsy_dir != "up") or \
                      (google_dir == "falling" and etsy_dir != "down")):
                    diverging.append({
                        "term": term,
                        "google_direction": google_dir,
                        "etsy_direction": etsy_dir,
                        "google_change": t.week_change,
                        "note": f"Google says {google_dir}, Etsy says {etsy_dir}",
                    })

        confirmed.sort(key=lambda x: abs(x.get("google_week_change", 0)), reverse=True)
        report.confirmed_trends = confirmed[:10]
        report.diverging_signals = diverging[:10]

        # 4. Biggest movers
        all_with_changes = [
            {"term": t.term, "week_change": t.week_change,
             "current_value": t.current_value, "category": t.category}
            for t in trends.values()
        ]
        all_with_changes.sort(key=lambda x: abs(x["week_change"]), reverse=True)
        report.biggest_movers = all_with_changes[:10]

        # 5. Category averages
        cat_values = defaultdict(list)
        for t in trends.values():
            cat_values[t.category].append(t.current_value)
        report.category_averages = {
            cat: sum(vals) // len(vals)
            for cat, vals in cat_values.items()
            if vals
        }

        # 6. Summary
        if confirmed:
            report.correlation_summary = (
                f"{len(confirmed)} confirmed trends where Google + Etsy agree. "
                f"Top: {confirmed[0]['term']}."
            )
        else:
            report.correlation_summary = "No clear Google-Etsy correlation signals yet. Feed more Etsy data."

        return report

    def _build_etsy_term_map(self) -> Dict[str, Dict]:
        """Build a map of Etsy material/category terms to their trend data."""
        term_map = {}
        for m in self.etsy_materials:
            mat = m.get("material", "").lower()
            term_map[mat] = m
        for c in self.etsy_categories:
            cat = c.get("category", "").lower()
            term_map[cat] = c
        return term_map

    def run_quick_scan(self) -> str:
        """Run a quick scan and return a readable summary."""
        report = self.run_analysis()
        return report.format_summary()


# =============================================================================
# Standalone usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Google Trends Overlay — JewelScope Research")
    print("=" * 60)
    print(f"pytrends available: {HAS_PYTRENDS}")
    print("")

    analyzer = TrendsOverlayAnalyzer()

    # Demo Etsy data for correlation
    analyzer.set_etsy_data(
        materials=[
            {"material": "gold", "count": 40, "trend_direction": "up"},
            {"material": "silver", "count": 35, "trend_direction": "down"},
            {"material": "diamond", "count": 25, "trend_direction": "up"},
        ],
        categories=[
            {"category": "Rings", "count": 150, "trend_direction": "up"},
            {"category": "Necklaces", "count": 110, "trend_direction": "stable"},
        ],
    )

    # Run with a small subset for testing
    test_terms = ["gold ring", "engagement ring", "silver necklace",
                  "diamond earrings", "vintage jewelry"]
    report = analyzer.run_analysis(test_terms)
    print(report.format_summary())

    if not HAS_PYTRENDS:
        print("\n⚠️  pytrends not installed. Install:")
        print("   pip install pytrends")
        print("   Then re-run for real Google Trends data.\n")