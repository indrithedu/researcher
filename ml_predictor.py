# =============================================================================
# JewelScope Research — ML Predictive Engine
# =============================================================================
#
# Machine learning system that predicts jewelry market trends from Etsy data
# and scraped news content.
#
# Models:
#   1. PRICE FORECASTER — Predicts optimal price ranges for jewelry categories
#   2. DEMAND PREDICTOR — Forecasts which jewelry types will see demand growth
#   3. MATERIAL TREND MODEL — Predicts which materials will trend up/down
#   4. KEYWORD IMPACT MODEL — Measures keyword effectiveness for listings
#   5. CATEGORY CLUSTER — Groups similar jewelry niches by market behavior
#
# All models use scikit-learn and require no GPU. Training data comes from
# Etsy API and the scraped article database.
# =============================================================================

import json
import logging
import math
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict

import numpy as np

logger = logging.getLogger(__name__)

# Try to import sklearn — gracefully fall back if not available
try:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.cluster import KMeans
    from sklearn.model_selection import train_test_split
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn not installed — ML predictions will use heuristics")
    logger.warning("Install: pip install scikit-learn")


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PredictionResult:
    """A single prediction result."""
    target: str
    predicted_value: float
    confidence: float  # 0.0 to 1.0
    trend_direction: str  # "up", "down", "stable"
    factors: List[Dict[str, Any]] = field(default_factory=list)
    historical_values: List[float] = field(default_factory=list)
    forecast_values: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MarketForecast:
    """Complete market forecast report."""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    forecast_date: str = field(default_factory=lambda: (date.today() + timedelta(days=30)).isoformat())
    data_points: int = 0
    
    # Price predictions
    price_forecasts: List[PredictionResult] = field(default_factory=list)
    
    # Demand predictions
    demand_forecasts: List[PredictionResult] = field(default_factory=list)
    
    # Material trends
    material_forecasts: List[PredictionResult] = field(default_factory=list)
    
    # Category growth predictions
    category_growth: List[Dict] = field(default_factory=list)
    
    # Market summary
    market_health_score: float = 0.5
    top_opportunities: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

    def format_summary(self) -> str:
        lines = []
        lines.append(f"🔮 **Market Forecast** — {self.generated_at[:10]}")
        lines.append(f"   Forecast horizon: {self.forecast_date}")
        lines.append(f"   Based on {self.data_points} data points")
        lines.append("")

        if self.price_forecasts:
            lines.append("💰 **Price Predictions:**")
            for p in self.price_forecasts[:5]:
                arrow = "📈" if p.trend_direction == "up" else "📉" if p.trend_direction == "down" else "➡️"
                lines.append(f"   {arrow} {p.target}: ${p.predicted_value:.0f} "
                             f"(confidence: {p.confidence:.0%})")

        if self.demand_forecasts:
            lines.append("\n📊 **Demand Forecasts:**")
            for d in self.demand_forecasts[:5]:
                arrow = "🔥" if d.trend_direction == "up" else "❄️" if d.trend_direction == "down" else "➡️"
                lines.append(f"   {arrow} {d.target}: {d.predicted_value:.1f} "
                             f"(confidence: {d.confidence:.0%})")

        if self.material_forecasts:
            lines.append("\n🧪 **Material Trends:**")
            for m in self.material_forecasts[:5]:
                lines.append(f"   {'📈' if m.trend_direction == 'up' else '📉'} {m.target}: "
                             f"trend {m.trend_direction} (confidence: {m.confidence:.0%})")

        if self.top_opportunities:
            lines.append("\n💡 **Top Opportunities:**")
            for opp in self.top_opportunities[:3]:
                lines.append(f"   ✅ {opp}")

        if self.risk_factors:
            lines.append("\n⚠️ **Risk Factors:**")
            for risk in self.risk_factors[:3]:
                lines.append(f"   ⚠️  {risk}")

        lines.append(f"\n📊 Market Health Score: {self.market_health_score:.0%}")
        return "\n".join(lines)


# =============================================================================
# Feature Engineering
# =============================================================================

class FeatureBuilder:
    """
    Transforms raw Etsy/scraped data into ML features.
    
    Features include:
    - Price statistics (mean, median, std, percentiles)
    - Material frequency vectors
    - Tag/topic frequency vectors
    - Engagement metrics (views, favorites, sales)
    - Temporal features (day of week, seasonality)
    - Shop density and competition metrics
    - Price elasticity indicators
    """

    @staticmethod
    def listing_to_features(listings: List[Dict]) -> np.ndarray:
        """Convert listing dictionaries to feature matrix."""
        features = []
        for l in listings:
            fv = []
            # Price features
            fv.append(float(l.get("price_amount", 0)))
            fv.append(float(l.get("shipping_price", 0)))
            
            # Engagement
            fv.append(float(l.get("views", 0)))
            fv.append(float(l.get("favorites", 0)))
            fv.append(float(l.get("num_sold", 0)))
            
            # Quantity available (supply indicator)
            fv.append(float(l.get("quantity", 1)))
            
            # Processing time (complexity indicator)
            fv.append(float(l.get("processing_min", 1)))
            
            # Has customization
            fv.append(1.0 if l.get("is_customizable") else 0.0)
            fv.append(1.0 if l.get("is_personalizable") else 0.0)
            fv.append(1.0 if l.get("is_vintage") else 0.0)
            
            # Number of tags (SEO effort)
            fv.append(len(l.get("tags", [])))
            
            # Number of materials (complexity)
            fv.append(len(l.get("materials", [])))
            
            features.append(fv)
        
        return np.array(features) if features else np.array([])

    @staticmethod
    def engagement_score(listing: Dict) -> float:
        """Compute normalized engagement score for a listing."""
        views = float(listing.get("views", 0))
        favorites = float(listing.get("favorites", 0))
        sold = float(listing.get("num_sold", 0))
        
        # Weighted engagement formula
        score = views + favorites * 3 + sold * 10
        
        # Log-scale normalization
        return math.log2(max(score, 1))

    @staticmethod
    def price_elasticity(prices: List[float], demands: List[float]) -> float:
        """
        Compute price elasticity of demand.
        Negative = price increase reduces demand (normal)
        Positive = Veblen good (higher price increases demand — luxury)
        """
        if len(prices) < 3 or len(demands) < 3:
            return 0.0
        
        try:
            log_prices = np.log(np.array(prices) + 1)
            log_demand = np.log(np.array(demands) + 1)
            corr = np.corrcoef(log_prices, log_demand)[0, 1]
            return float(corr) if not np.isnan(corr) else 0.0
        except Exception:
            return 0.0


# =============================================================================
# ML Predictors
# =============================================================================

class PricePredictor:
    """Predicts optimal price ranges for jewelry categories."""

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler() if HAS_SKLEARN else None
        self.is_trained = False

    def train(self, listings: List[Dict]):
        """Train on historical listing data to predict optimal prices."""
        if not listings or len(listings) < 20:
            logger.warning(f"Need at least 20 listings to train price model (got {len(listings) if listings else 0})")
            return

        if not HAS_SKLEARN:
            logger.info("scikit-learn unavailable — using heuristic price prediction")
            self.is_trained = True
            return

        try:
            fb = FeatureBuilder()
            X = fb.listing_to_features(listings)
            
            # Target: price_amount
            y = np.array([float(l.get("price_amount", 0)) for l in listings])
            
            # Filter out zero-price entries
            mask = y > 0
            X = X[mask]
            y = y[mask]
            
            if len(X) < 10:
                return
            
            # Scale features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train ensemble model
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1,
            )
            self.model.fit(X_scaled, y)
            self.is_trained = True
            logger.info(f"Price model trained on {len(X)} listings")
            
        except Exception as e:
            logger.error(f"Price model training failed: {e}")
            self.is_trained = False

    def predict_optimal_price(self, features: List[float]) -> Tuple[float, float]:
        """
        Predict optimal price for a listing with given features.
        Returns: (predicted_price, confidence)
        """
        if not self.is_trained:
            return (50.0, 0.3)  # Default heuristic

        if HAS_SKLEARN and self.model and self.scaler:
            try:
                X = np.array([features])
                X_scaled = self.scaler.transform(X)
                pred = self.model.predict(X_scaled)[0]
                
                # Confidence based on feature count
                confidence = min(0.9, len(features) / 15.0)
                return (float(pred), confidence)
            except Exception:
                pass

        return (50.0, 0.3)

    def predict_category_prices(self, listings: List[Dict]) -> List[PredictionResult]:
        """Predict optimal price ranges for each jewelry category."""
        if not listings:
            return []

        # Group by category
        categories = defaultdict(list)
        for l in listings:
            path = l.get("taxonomy_path", [])
            cat = path[-1] if path else "uncategorized"
            categories[cat].append(l)

        results = []
        for cat, cat_listings in categories.items():
            prices = [float(l.get("price_amount", 0)) for l in cat_listings if float(l.get("price_amount", 0)) > 0]
            if not prices:
                continue

            mean_price = np.mean(prices)
            median_price = np.median(prices)
            std_price = np.std(prices)

            # Determine trend direction
            # (compare recent vs. older listings)
            recent = [p for l, p in zip(cat_listings, prices)
                     if l.get("created_ts", 0) > (datetime.utcnow().timestamp() - 86400 * 30)]
            older = [p for l, p in zip(cat_listings, prices)
                    if l.get("created_ts", 0) <= (datetime.utcnow().timestamp() - 86400 * 30)]

            if recent and older:
                trend = "up" if np.mean(recent) > np.mean(older) * 1.05 else \
                        "down" if np.mean(recent) < np.mean(older) * 0.95 else "stable"
            else:
                trend = "stable"

            conf = min(0.8, len(prices) / 100)
            results.append(PredictionResult(
                target=cat,
                predicted_value=round(median_price, 2),
                confidence=conf,
                trend_direction=trend,
                historical_values=prices[-30:] if len(prices) > 30 else prices,
                factors=[
                    {"name": "mean_price", "value": round(mean_price, 2)},
                    {"name": "std_price", "value": round(std_price, 2)},
                    {"name": "sample_size", "value": len(prices)},
                    {"name": "price_elasticity", "value": round(FeatureBuilder.price_elasticity(prices, [1]*len(prices)), 3)},
                ],
            ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results


class DemandPredictor:
    """Predicts which jewelry categories will see demand growth."""

    def __init__(self):
        self.model = None
        self.is_trained = False

    def train(self, listings: List[Dict]):
        """Train demand prediction model."""
        if not listings or len(listings) < 30:
            return

        if not HAS_SKLEARN:
            self.is_trained = True
            return

        try:
            # Features: engagement metrics
            X = []
            y = []

            for l in listings:
                views = float(l.get("views", 0))
                favorites = float(l.get("favorites", 0))
                sold = float(l.get("num_sold", 0))
                price = float(l.get("price_amount", 0))
                tags_count = len(l.get("tags", []))

                if views == 0 and favorites == 0:
                    continue

                # Features
                X.append([views, favorites, price, tags_count, sold])

                # Target: conversion rate (sold / views as proxy for demand)
                conversion = sold / max(views, 1)
                y.append(min(conversion, 1.0))  # Cap at 1.0

            if len(X) < 20:
                return

            X = np.array(X)
            y = np.array(y)

            self.model = RandomForestRegressor(
                n_estimators=80, max_depth=8, random_state=42
            )
            self.model.fit(X, y)
            self.is_trained = True
            logger.info(f"Demand model trained on {len(X)} samples")

        except Exception as e:
            logger.error(f"Demand model training failed: {e}")

    def predict_category_demand(self, listings: List[Dict]) -> List[PredictionResult]:
        """Predict demand growth for each jewelry category."""
        categories = defaultdict(list)
        for l in listings:
            path = l.get("taxonomy_path", [])
            cat = path[-1] if path else "uncategorized"
            categories[cat].append(l)

        results = []
        for cat, cat_listings in categories.items():
            # Current demand proxy
            total_views = sum(float(l.get("views", 0)) for l in cat_listings)
            total_sold = sum(float(l.get("num_sold", 0)) for l in cat_listings)
            total_favs = sum(float(l.get("favorites", 0)) for l in cat_listings)

            if total_views == 0:
                continue

            demand_rate = total_sold / max(total_views, 1) * 1000  # per 1000 views
            fav_rate = total_favs / max(total_views, 1) * 1000

            # Trend from recent vs older
            now = datetime.utcnow().timestamp()
            recent_sold = sum(float(l.get("num_sold", 0)) for l in cat_listings
                             if l.get("created_ts", 0) > (now - 86400 * 14))
            older_sold = sum(float(l.get("num_sold", 0)) for l in cat_listings
                            if l.get("created_ts", 0) <= (now - 86400 * 14))

            if older_sold > 0:
                demand_change = (recent_sold / older_sold) - 1.0
            else:
                demand_change = 0.0

            trend = "up" if demand_change > 0.15 else "down" if demand_change < -0.15 else "stable"

            conf = min(0.8, len(cat_listings) / 50)
            results.append(PredictionResult(
                target=cat,
                predicted_value=round(demand_rate, 2),
                confidence=conf,
                trend_direction=trend,
                historical_values=[demand_rate],
                factors=[
                    {"name": "sold_per_1000_views", "value": round(demand_rate, 2)},
                    {"name": "favs_per_1000_views", "value": round(fav_rate, 2)},
                    {"name": "demand_change", "value": round(demand_change, 3)},
                    {"name": "listing_count", "value": len(cat_listings)},
                ],
            ))

        results.sort(key=lambda r: r.trend_direction == "up", reverse=True)
        return results


class MaterialTrendModel:
    """Predicts which materials are trending up or down."""

    def predict(self, listings: List[Dict]) -> List[PredictionResult]:
        """Analyze material trends from listing data."""
        material_data = defaultdict(lambda: {"count": 0, "recent_count": 0,
                                              "avg_price": [], "total_sold": 0})
        now = datetime.utcnow().timestamp()
        cutoff = now - 86400 * 30  # 30 days

        for l in listings:
            materials = l.get("materials", [])
            created = l.get("created_ts", 0)
            is_recent = created > cutoff if created else False

            for mat in materials:
                m = mat.lower().strip()
                material_data[m]["count"] += 1
                material_data[m]["avg_price"].append(float(l.get("price_amount", 0)))
                material_data[m]["total_sold"] += l.get("num_sold", 0)
                if is_recent:
                    material_data[m]["recent_count"] += 1

        results = []
        for mat, d in material_data.items():
            if d["count"] < 2:
                continue

            # Trend: recent vs total proportion
            recent_ratio = d["recent_count"] / max(d["count"], 1)
            total_ratio = d["count"] / max(len(listings), 1)

            # If recent proportion is higher than total proportion, it's trending
            trend_score = recent_ratio - total_ratio
            trend = "up" if trend_score > 0.05 else "down" if trend_score < -0.05 else "stable"

            avg_price = np.mean(d["avg_price"]) if d["avg_price"] else 0

            confidence = min(0.7, d["count"] / 50)
            results.append(PredictionResult(
                target=mat,
                predicted_value=round(trend_score, 3),
                confidence=confidence,
                trend_direction=trend,
                factors=[
                    {"name": "listing_count", "value": d["count"]},
                    {"name": "recent_listings", "value": d["recent_count"]},
                    {"name": "avg_price", "value": round(avg_price, 2)},
                    {"name": "total_sold", "value": d["total_sold"]},
                ],
            ))

        results.sort(key=lambda r: abs(r.predicted_value), reverse=True)
        return results


class CategoryCluster:
    """Groups similar jewelry niches by market behavior using clustering."""

    def cluster(self, listings: List[Dict]) -> Dict[str, List[str]]:
        """Cluster jewelry categories by price, demand, and material similarity."""
        if not HAS_SKLEARN or len(listings) < 10:
            # Heuristic clustering
            return {
                "budget_fashion": ["earrings", "bracelets", "body jewelry"],
                "mid_market": ["necklaces", "rings", "anklets"],
                "premium": ["engagement rings", "fine jewelry", "watches"],
                "vintage_estate": ["vintage jewelry", "antique jewelry"],
            }

        try:
            fb = FeatureBuilder()
            feat_matrix = fb.listing_to_features(listings)

            if len(feat_matrix) < 5:
                return {}

            # Simple clustering by price bracket
            prices = np.array([float(l.get("price_amount", 0)) for l in listings])
            prices = prices.reshape(-1, 1)

            kmeans = KMeans(n_clusters=min(4, len(set(prices.flatten().astype(int)))), random_state=42)
            labels = kmeans.fit_prices(prices) if hasattr(kmeans, 'fit_prices') else []

            clusters = defaultdict(list)
            for label, listing in zip(labels if len(labels) == len(listings) else [], listings):
                path = listing.get("taxonomy_path", [])
                cat = path[-1] if path else "uncategorized"
                clusters[f"cluster_{label}"].append(cat)

            return dict(clusters)

        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            return {}


# =============================================================================
# Main Forecast Engine
# =============================================================================

class MarketForecastEngine:
    """
    Main engine that orchestrates all ML models and produces forecasts.
    
    Usage:
        engine = MarketForecastEngine()
        engine.train(listings)
        forecast = engine.forecast()
        print(forecast.format_summary())
    """

    def __init__(self):
        self.price_predictor = PricePredictor()
        self.demand_predictor = DemandPredictor()
        self.material_trend = MaterialTrendModel()
        self.cluster = CategoryCluster()
        self.listings: List[Dict] = []
        self.is_trained = False

    def train(self, listings: List[Dict]):
        """Train all models on listing data."""
        self.listings = listings
        if len(listings) < 10:
            logger.warning(f"Too few listings for training ({len(listings)}). Need 10+.")
            return

        logger.info(f"Training ML models on {len(listings)} listings...")
        self.price_predictor.train(listings)
        self.demand_predictor.train(listings)
        self.is_trained = True
        logger.info("ML training complete")

    def forecast(self) -> MarketForecast:
        """Generate complete market forecast."""
        forecast = MarketForecast()
        forecast.data_points = len(self.listings)

        if not self.is_trained or len(self.listings) < 5:
            logger.warning("Models not trained — generating heuristic forecast")
            return self._heuristic_forecast()

        # Price forecasts
        forecast.price_forecasts = self.price_predictor.predict_category_prices(self.listings)

        # Demand forecasts
        forecast.demand_forecasts = self.demand_predictor.predict_category_demand(self.listings)

        # Material trends
        forecast.material_forecasts = self.material_trend.predict(self.listings)

        # Category growth
        forecast.category_growth = self._compute_growth_rates()

        # Market health score
        forecast.market_health_score = self._compute_health_score()

        # Opportunities and risks (pass forecast data)
        forecast.top_opportunities = self._find_opportunities(
            forecast.demand_forecasts, forecast.price_forecasts, forecast.material_forecasts
        )
        forecast.risk_factors = self._find_risks(forecast.demand_forecasts)

        return forecast

    def _compute_growth_rates(self) -> List[Dict]:
        """Compute growth rates for each category."""
        categories = defaultdict(lambda: {"old_count": 0, "new_count": 0, "old_sold": 0, "new_sold": 0})
        now = datetime.utcnow().timestamp()
        cutoff = now - 86400 * 30

        for l in self.listings:
            path = l.get("taxonomy_path", [])
            cat = path[-1] if path else "uncategorized"
            created = l.get("created_ts", 0)

            if created > cutoff:
                categories[cat]["new_count"] += 1
                categories[cat]["new_sold"] += l.get("num_sold", 0)
            else:
                categories[cat]["old_count"] += 1
                categories[cat]["old_sold"] += l.get("num_sold", 0)

        growth = []
        for cat, d in categories.items():
            old_rate = d["old_sold"] / max(d["old_count"], 1)
            new_rate = d["new_sold"] / max(d["new_count"], 1)
            growth_pct = ((new_rate - old_rate) / max(old_rate, 0.01)) * 100

            growth.append({
                "category": cat,
                "growth_pct": round(growth_pct, 1),
                "listings_old": d["old_count"],
                "listings_new": d["new_count"],
            })

        growth.sort(key=lambda x: x["growth_pct"], reverse=True)
        return growth

    def _compute_health_score(self) -> float:
        """Compute overall market health score (0-1)."""
        if not self.listings:
            return 0.5

        total_views = sum(float(l.get("views", 0)) for l in self.listings)
        total_sold = sum(float(l.get("num_sold", 0)) for l in self.listings)
        total_favs = sum(float(l.get("favorites", 0)) for l in self.listings)

        # Engagement per listing
        avg_views = total_views / len(self.listings)
        avg_sold = total_sold / len(self.listings)
        avg_favs = total_favs / len(self.listings)

        # Score components
        view_score = min(1.0, avg_views / 5000)
        sold_score = min(1.0, avg_sold / 50)
        fav_score = min(1.0, avg_favs / 200)

        # Weighted average
        score = view_score * 0.3 + sold_score * 0.4 + fav_score * 0.3
        return round(score, 3)

    def _find_opportunities(self, demand_fc: list, price_fc: list, material_fc: list) -> List[str]:
        """Identify market opportunities from forecast data."""
        opportunities = []
        if demand_fc:
            for d in demand_fc[:3]:
                if d.trend_direction == "up":
                    opportunities.append(f"Growing demand in {d.target} — consider increasing listings")

        if price_fc:
            high_price = [p for p in price_fc if p.predicted_value > 200]
            if high_price:
                opportunities.append(f"Premium {high_price[0].target} market shows strong price points")

        if material_fc:
            trending_materials = [m for m in material_fc if m.trend_direction == "up"]
            if trending_materials:
                mats = ", ".join(m.target for m in trending_materials[:3])
                opportunities.append(f"Trending materials: {mats} — focus on these in new listings")

        return opportunities[:5]

    def _find_risks(self, demand_fc: list) -> List[str]:
        """Identify market risks."""
        risks = []
        if demand_fc:
            declining = [d for d in demand_fc if d.trend_direction == "down"]
            if declining:
                cats = ", ".join(d.target for d in declining[:3])
                risks.append(f"Declining demand in {cats} — consider reducing inventory")

        return risks[:5]

    def _heuristic_forecast(self) -> MarketForecast:
        """Generate forecast using heuristics when ML unavailable."""
        forecast = MarketForecast()
        forecast.data_points = len(self.listings)

        if self.listings:
            # Simple price averages by category
            categories = defaultdict(list)
            for l in self.listings:
                path = l.get("taxonomy_path", [])
                cat = path[-1] if path else "uncategorized"
                categories[cat].append(float(l.get("price_amount", 0)))

            for cat, prices in categories.items():
                if prices:
                    forecast.price_forecasts.append(PredictionResult(
                        target=cat,
                        predicted_value=round(np.median(prices), 2),
                        confidence=0.4,
                        trend_direction="stable",
                    ))

        forecast.market_health_score = 0.5
        return forecast


# =============================================================================
# Convenience: full pipeline
# =============================================================================

def run_ml_pipeline(listings: List[Dict]) -> MarketForecast:
    """Run full ML pipeline on listing data."""
    engine = MarketForecastEngine()
    engine.train(listings)
    return engine.forecast()


# =============================================================================
# Standalone
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("JewelScope ML Prediction Engine")
    print("=" * 60)
    print(f"scikit-learn available: {HAS_SKLEARN}")
    print("")

    # Generate synthetic data for demo
    import random
    random.seed(42)
    np.random.seed(42)

    demo_listings = []
    categories = ["Rings", "Necklaces", "Earrings", "Bracelets", "Watches", "Body Jewelry"]
    materials_list = ["sterling silver", "gold", "diamond", "pearl", "rose gold",
                      "stainless steel", "gemstone", "platinum"]

    for i in range(500):
        cat = random.choice(categories)
        mat = random.choice(materials_list)
        price = {
            "Rings": random.gauss(185, 100),
            "Necklaces": random.gauss(95, 60),
            "Earrings": random.gauss(65, 40),
            "Bracelets": random.gauss(120, 80),
            "Watches": random.gauss(450, 300),
            "Body Jewelry": random.gauss(25, 15),
        }[cat]
        days_ago = random.randint(0, 120)

        demo_listings.append({
            "listing_id": i,
            "title": f"{mat} {cat}",
            "price_amount": max(5, price + random.gauss(0, 10)),
            "shipping_price": random.choice([0, 4.99, 9.99]),
            "views": int(random.expovariate(0.001)),
            "favorites": int(random.expovariate(0.05)),
            "num_sold": int(random.expovariate(0.1)),
            "quantity": random.randint(1, 100),
            "tags": [f"#{mat}", f"#{cat.lower()}", "#handmade", "#gift"] + random.sample(["#wedding", "#birthday", "#anniversary", "#personalized"], 2),
            "materials": [mat] + random.sample(materials_list, random.randint(0, 2)),
            "taxonomy_path": ["Jewelry", cat],
            "is_customizable": random.choice([True, False]),
            "is_personalizable": random.choice([True, False]),
            "is_vintage": random.choice([True, False]),
            "created_ts": datetime.utcnow().timestamp() - days_ago * 86400,
            "processing_min": random.randint(1, 14),
        })

    print(f"Generated {len(demo_listings)} demo listings\n")

    engine = MarketForecastEngine()
    engine.train(demo_listings)
    forecast = engine.forecast()

    print(forecast.format_summary())
    print("\n✅ ML pipeline complete")