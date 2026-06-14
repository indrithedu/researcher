# =============================================================================
# JewelScope Research — Scheduler Module
# =============================================================================
# Handles daily automated runs using APScheduler.
# Can be run as a background thread from the main app or as a standalone
# process for server deployments.
# =============================================================================

import os
import json
import logging
import threading
from datetime import date, datetime
from typing import Optional, Callable

import yaml

logger = logging.getLogger(__name__)


class ResearchScheduler:
    """
    Schedules daily research runs.
    Uses APScheduler with a configurable cron expression.
    """

    def __init__(self, config: dict, run_callback: Callable):
        """
        Args:
            config: Full app config dict
            run_callback: Function to call when a run is triggered
        """
        self.config = config
        self.run_callback = run_callback
        self.scheduler = None
        self._running = False
        self._thread = None

        sched_config = config.get("scheduling", {})
        self.enabled = sched_config.get("enabled", True)
        self.cron = sched_config.get("cron", "0 7 * * *")
        self.interval_hours = sched_config.get("interval_hours", 24)

    def start(self):
        """Start the scheduler in a background thread."""
        if not self.enabled:
            logger.info("Scheduler is disabled in config")
            return

        if self._running:
            logger.warning("Scheduler is already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._thread.start()
        logger.info(f"Scheduler started with cron: {self.cron}")

    def _run_scheduler(self):
        """Run the APScheduler in a background thread."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            self.scheduler = BackgroundScheduler()

            # Parse cron expression (format: minute hour day month day_of_week)
            parts = self.cron.split()
            if len(parts) == 5:
                trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                )
                self.scheduler.add_job(
                    self.run_callback,
                    trigger,
                    id="daily_research",
                    name="Daily JewelScope Research Run",
                    replace_existing=True,
                )
                logger.info(f"Scheduled job with cron: {self.cron}")
            else:
                # Fallback: interval-based
                self.scheduler.add_job(
                    self.run_callback,
                    "interval",
                    hours=self.interval_hours,
                    id="interval_research",
                    name="Interval JewelScope Research Run",
                    replace_existing=True,
                )
                logger.info(f"Scheduled job every {self.interval_hours} hours")

            self.scheduler.start()

            # Keep thread alive
            while self._running:
                import time
                time.sleep(10)

        except ImportError:
            logger.warning("APScheduler not installed — falling back to simple loop")
            self._simple_loop()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            self._simple_loop()

    def _simple_loop(self):
        """Simple fallback scheduler using time.sleep."""
        import time
        last_run = datetime.now()

        while self._running:
            now = datetime.now()
            elapsed = (now - last_run).total_seconds() / 3600

            if elapsed >= self.interval_hours:
                logger.info("Simple scheduler: triggering daily run")
                try:
                    self.run_callback()
                except Exception as e:
                    logger.error(f"Simple scheduler run failed: {e}")
                last_run = now

            time.sleep(60)  # Check every minute

    def stop(self):
        """Stop the scheduler gracefully."""
        self._running = False
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass
        logger.info("Scheduler stopped")

    def next_run_time(self) -> Optional[str]:
        """Get the next scheduled run time."""
        if self.scheduler:
            try:
                job = self.scheduler.get_job("daily_research")
                if job and job.next_run_time:
                    return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        return None


# =============================================================================
# Convenience: Create and start scheduler from config
# =============================================================================

def create_scheduler(config_path: str = "config.yaml", run_callback: Callable = None) -> ResearchScheduler:
    """Load config and create a scheduler."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return ResearchScheduler(config, run_callback)
