# =============================================================================
# Tests: Database Module
# =============================================================================

import os
import json
from datetime import date, datetime

import pytest

from database import DatabaseManager, ScrapeSession, Article, CommodityPrice, Report


class TestDatabaseManager:
    """Test database creation, schema, and CRUD operations."""

    def test_initialization(self, temp_db_path):
        """Database should initialize and create tables."""
        db = DatabaseManager(temp_db_path)
        assert os.path.exists(temp_db_path)

    def test_get_stats_empty(self, temp_db_path):
        """Fresh database should show zero counts."""
        db = DatabaseManager(temp_db_path)
        stats = db.get_stats()
        assert stats["total_sessions"] == 0
        assert stats["total_articles"] == 0
        assert stats["total_reports"] == 0
        assert stats["total_commodity_prices"] == 0

    def test_start_and_complete_session(self, temp_db_path):
        """Create a session and mark it complete."""
        db = DatabaseManager(temp_db_path)
        session_id = db.start_session(trigger="manual")
        assert session_id == 1

        db.complete_session(
            session_id=session_id,
            status="success",
            succeeded=5,
            failed=0,
            articles=20,
            errors=[],
        )

        stats = db.get_stats()
        assert stats["total_sessions"] == 1

        sessions = db.get_recent_sessions()
        assert len(sessions) == 1
        assert sessions[0].status == "success"
        assert sessions[0].sources_succeeded == 5

    def test_session_with_errors(self, temp_db_path):
        """Session with partial failures."""
        db = DatabaseManager(temp_db_path)
        session_id = db.start_session(trigger="manual")
        db.complete_session(
            session_id=session_id,
            status="partial",
            succeeded=3,
            failed=2,
            articles=15,
            errors=["Source X blocked (403)", "Source Y timeout"],
        )

        sessions = db.get_recent_sessions()
        assert sessions[0].sources_failed == 2
        assert sessions[0].error_log is not None
        errors = json.loads(sessions[0].error_log)
        assert len(errors) == 2

    def test_save_and_retrieve_articles(self, temp_db_path):
        """Save articles and retrieve them by session."""
        db = DatabaseManager(temp_db_path)
        session_id = db.start_session()

        articles = [
            {
                "source_name": "Test Source",
                "source_url": "https://example.com",
                "title": "Test Article 1",
                "url": "https://example.com/article1",
                "published_date": "2024-12-01",
                "summary": "Summary 1",
                "category": "jewelry",
                "is_headline": True,
            },
            {
                "source_name": "Test Source 2",
                "source_url": "https://example2.com",
                "title": "Test Article 2",
                "url": "https://example.com/article2",
                "published_date": "2024-12-02",
                "summary": "Summary 2",
                "category": "etsy",
                "is_headline": False,
            },
        ]

        db.save_articles(session_id, articles)

        fetched = db.get_articles_by_session(session_id)
        assert len(fetched) == 2
        assert fetched[0].title == "Test Article 1"
        assert fetched[0].source_name == "Test Source"

    def test_save_and_get_commodity_prices(self, temp_db_path):
        """Save commodity prices and retrieve latest."""
        db = DatabaseManager(temp_db_path)

        prices = [
            {"commodity": "gold", "price_usd": 2345.50, "unit": "oz",
             "source": "https://kitco.com"},
            {"commodity": "silver", "price_usd": 28.75, "unit": "oz",
             "source": "https://kitco.com"},
            {"commodity": "platinum", "price_usd": 945.20, "unit": "oz",
             "source": "https://kitco.com"},
        ]
        db.save_commodity_prices(prices)

        latest = db.get_latest_commodity_prices()
        assert "gold" in latest
        assert "silver" in latest
        assert "platinum" in latest
        assert latest["gold"] == 2345.50

    def test_price_history(self, temp_db_path):
        """Get price history for a commodity."""
        db = DatabaseManager(temp_db_path)

        from datetime import timedelta

        # Add prices on different days
        for i in range(3):
            db.save_commodity_prices([{
                "commodity": "gold",
                "price_usd": 2300.0 + i * 20,
                "unit": "oz",
                "source": "test",
            }])

        history = db.get_price_history("gold", days=30)
        assert len(history) >= 1

    def test_save_and_get_report(self, temp_db_path):
        """Save a report and retrieve it."""
        db = DatabaseManager(temp_db_path)
        session_id = db.start_session()

        report_id = db.save_report(
            session_id=session_id,
            report_date=date.today(),
            html_path="/tmp/report.html",
            pdf_path="/tmp/report.pdf",
            metadata={"total_articles": 10, "sources_ok": 3, "failed": 1},
        )

        assert report_id == 1

        reports = db.get_recent_reports()
        assert len(reports) == 1
        assert reports[0].report_date == date.today()

        meta = reports[0].get_metadata()
        assert meta["total_articles"] == 10

    def test_report_by_date(self, temp_db_path):
        """Get report by specific date."""
        db = DatabaseManager(temp_db_path)
        session_id = db.start_session()

        db.save_report(
            session_id=session_id,
            report_date=date(2024, 12, 1),
            html_path="/tmp/r.html",
        )

        found = db.get_report_by_date(date(2024, 12, 1))
        assert found is not None
        assert found.report_date == date(2024, 12, 1)

        not_found = db.get_report_by_date(date(2024, 1, 1))
        assert not_found is None

    def test_multiple_sessions(self, temp_db_path):
        """Multiple sessions should be tracked independently."""
        db = DatabaseManager(temp_db_path)

        id1 = db.start_session(trigger="manual")
        id2 = db.start_session(trigger="scheduled")

        assert id1 != id2
        assert id2 == 2

        db.complete_session(id1, "success", 3, 0, 10)
        db.complete_session(id2, "failed", 0, 3, 0)

        recent = db.get_recent_sessions(limit=5)
        assert len(recent) == 2
        assert recent[0].status == "failed"  # Most recent first
        assert recent[1].status == "success"

    def test_schema_reentrant(self, temp_db_path):
        """Creating a database twice should not error."""
        db1 = DatabaseManager(temp_db_path)
        db2 = DatabaseManager(temp_db_path)  # Should work fine
        stats = db2.get_stats()
        assert stats is not None
