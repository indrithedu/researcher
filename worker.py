# =============================================================================
# JewelScope Research — Huey Worker
# =============================================================================
# Runs background tasks for JewelScope.
# Usage: huey_consumer.py worker.huey
# =============================================================================

import os
import logging
from huey import crontab
from logic import huey, load_config, run_full_scrape

logger = logging.getLogger(__name__)

@huey.task()
def run_research_scan(trigger="manual"):
    """Background task to run a full research scan."""
    logger.info(f"Starting research scan triggered via {trigger}")
    config = load_config()
    try:
        result = run_full_scrape(config)
        logger.info(f"Scan complete: {result.get('total_articles', 0)} articles found.")
        return result
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        raise

# Import scheduler to register periodic tasks at module level
import scheduler
