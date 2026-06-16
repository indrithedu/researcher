# =============================================================================
# JewelScope Research — Core Logic
# =============================================================================

import os
import sys
import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import yaml
from huey import SqliteHuey

# Ensure we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.yaml")
DB_PATH = os.path.join(APP_DIR, "databases", "jewelscope.db")
HUEY_PATH = os.path.join(APP_DIR, "databases", "huey.db")
REPORT_DIR = os.path.join(APP_DIR, "reports")

# Ensure directories exist
os.makedirs(os.path.join(APP_DIR, "databases"), exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# Initialize Huey with SQLite
huey = SqliteHuey(filename=HUEY_PATH)


def load_config() -> dict:
    """Load the YAML config file."""
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def save_config(config: dict):
    """Save the YAML config file."""
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_database():
    """Get or create the database manager."""
    from database import DatabaseManager
    return DatabaseManager(DB_PATH)


def get_anti_detect_client(config: dict = None):
    """Get or create the anti-detection HTTP client."""
    from anti_detect import AntiDetectClient
    return AntiDetectClient(config or load_config())


def run_full_scrape(config: dict) -> dict:
    """
    Run a full scrape across all sources.
    Returns a summary dict with results.
    """
    import asyncio
    from scraper import JewelScopeScraper
    from anti_detect import AntiDetectClient

    db = get_database()
    client = AntiDetectClient(config)
    scraper = JewelScopeScraper(config, client)

    # Start database session
    session_id = db.start_session(trigger="manual")

    # Run all scrapers (async)
    results = asyncio.run(scraper.run_all())
    all_articles = scraper.get_all_articles()

    # Calculate stats
    succeeded = sum(1 for v in results.values() if len(v) > 0)
    failed = sum(1 for v in results.values() if len(v) == 0)
    total_articles = len(all_articles)

    # Save articles to database
    if all_articles:
        db.save_articles(session_id, all_articles)

    # Separate commodity prices
    commodity_prices = [a for a in all_articles if a.get("category") == "commodity"]
    volatility_alerts = []
    if commodity_prices:
        formatted_prices = []
        for a in commodity_prices:
            name = a["source_name"].split("—")[-1].strip().lower().split()[0] if "—" in a["source_name"] else a["source_name"]
            try:
                price = float(a["title"].split("$")[-1].replace(",", "").split()[0])
            except (ValueError, IndexError):
                price = 0.0
            
            formatted_prices.append({
                "commodity": name,
                "price_usd": price,
                "unit": "oz",
                "source": a["source_url"],
            })
            
        db.save_commodity_prices(formatted_prices)
        
        # Phase 4: Anomaly Detection
        for p in formatted_prices:
            z_score = db.get_commodity_anomaly_score(p["commodity"])
            if abs(z_score) > 2.0:
                volatility_alerts.append({
                    "commodity": p["commodity"],
                    "z_score": z_score,
                    "price": p["price_usd"],
                    "type": "Crash" if z_score < -2.0 else "Surge"
                })

    # Complete session
    errors = getattr(scraper, "errors", [])
    db.complete_session(
        session_id=session_id,
        status="partial" if failed > 0 else "success",
        succeeded=succeeded,
        failed=failed,
        articles=total_articles,
        errors=[str(e) for e in errors],
    )

    # Generate report
    from report_generator import ReportGenerator
    report_gen = ReportGenerator(config)

    headlines = scraper.get_headlines(top_n=10)
    etsy_intel = scraper.get_etsy_intelligence()

    html_path = report_gen.generate_html(
        articles=all_articles,
        headlines=headlines,
        etsy_intel=etsy_intel,
        commodity_prices=commodity_prices,
        session_summary={
            "sources_succeeded": succeeded,
            "sources_failed": failed,
            "total_articles": total_articles,
            "volatility_alerts": volatility_alerts,
        },
        report_date=date.today(),
    )

    # Try PDF
    pdf_path = report_gen.generate_pdf(html_path)

    # Save report record
    db.save_report(
        session_id=session_id,
        report_date=date.today(),
        html_path=html_path,
        pdf_path=pdf_path,
        metadata={
            "total_articles": total_articles,
            "headlines": len(headlines),
            "etsy_intel": len(etsy_intel),
            "commodity_prices": len(commodity_prices),
            "sources_succeeded": succeeded,
            "sources_failed": failed,
            "volatility_alerts": volatility_alerts,
        },
    )

    return {
        "session_id": session_id,
        "total_articles": total_articles,
        "sources_succeeded": succeeded,
        "sources_failed": failed,
        "headlines": headlines,
        "etsy_intel": etsy_intel,
        "commodity_prices": commodity_prices,
        "all_articles": all_articles,
        "html_path": html_path,
        "pdf_path": pdf_path,
        "errors": errors,
    }
