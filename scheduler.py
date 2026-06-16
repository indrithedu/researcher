# =============================================================================
# JewelScope Research — Scheduler Module (Huey Edition)
# =============================================================================
# Handles daily automated runs using Huey periodic tasks.
# =============================================================================

import os
import logging
from huey import crontab
from logic import huey, load_config

logger = logging.getLogger(__name__)

config = load_config()
sched_config = config.get("scheduling", {})
cron_str = sched_config.get("cron", "0 7 * * *")
parts = cron_str.split()

if sched_config.get("enabled", True) and len(parts) == 5:
    @huey.periodic_task(crontab(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4]
    ))
    def scheduled_research_scan():
        from worker import run_research_scan
        run_research_scan(trigger="scheduled")
else:
    logger.info("Scheduling is disabled or invalid cron in config. Periodic task not registered.")

# This module can also be used to trigger manual scans via huey
def trigger_manual_scan():
    from worker import run_research_scan
    return run_research_scan(trigger="manual")
