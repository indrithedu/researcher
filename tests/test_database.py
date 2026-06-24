"""
E2E tests for the database module — uses in-memory SQLite, no API keys.
Tests: CRUD operations, session management, article storage, commodity prices,
keyword momentum, and report storage.
"""

import unittest
import sys
import os
import json
import tempfile
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDatabaseSetup(unittest.TestCase):
    """Test database initialization and schema creation."""

    def setUp(self):
        from database import DatabaseManager
        # Use a temporary file for each test
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        os.unlink(self.db_path)

    def test_database_created(self):
        """Verify the database file was created."""
        self.assertTrue(os.path.exists(self.db_path))

    def test_tables_exist(self):
        """Verify all expected tables were created."""
        tables = self.db.get_table_names()
        expected = {"scrape_sessions", "articles", "reports", "commodity_prices"}
        for table in expected:
            self.assertIn(table, tables, f"Missing table: {table}")

    def test_get_stats_empty(self):
        """Stats should work on a fresh database."""
        stats = self.db.get_stats()
        self.assertEqual(stats.get("total_articles", 0), 0)
        self.assertEqual(stats.get("total_sessions", 0), 0)
        self.assertEqual(stats.get("total_reports", 0), 0)


class TestSessions(unittest.TestCase):
    """Test scrape session lifecycle."""

    def setUp(self):
        from database import DatabaseManager
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        os.unlink(self.db_path)

    def test_start_session(self):
        session_id = self.db.start_session(trigger="manual")
        self.assertIsNotNone(session_id)
        self.assertGreater(session_id, 0)

    def test_start_session_with_schedule(self):
        session_id = self.db.start_session(trigger="scheduled")
        self.assertIsNotNone(session_id)

    def test_complete_session(self):
        session_id = self.db.start_session(trigger="manual")
        self.db.complete_session(
            session_id=session_id,
            status="success",
            succeeded=5,
            failed=1,
            articles=50,
            errors=[],
        )
        stats = self.db.get_stats()
        self.assertGreater(stats.get("total_sessions", 0), 0)
        self.assertEqual(stats.get("total_articles", 0), 50)

    def test_complete_session_with_errors(self):
        session_id = self.db.start_session(trigger="manual")
        self.db.complete_session(
            session_id=session_id,
            status="partial",
            succeeded=3,
            failed=2,
            articles=30,
            errors=["Source X failed: connection timeout"],
        )
        sess = self.db.get_session(session_id)
        self.assertEqual(sess.status, "partial")

    def test_latest_session(self):
        session_id = self.db.start_session(trigger="manual")
        self.db.complete_session(
            session_id=session_id, status="success",
            succeeded=5, failed=0, articles=20, errors=[],
        )
        stats = self.db.get_stats()
        self.assertIsNotNone(stats.get("latest_session"))


class TestArticles(unittest.TestCase):
    """Test article CRUD operations."""

    def setUp(self):
        from database import DatabaseManager
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.db = DatabaseManager(self.db_path)
        self.session_id = self.db.start_session(trigger="manual")

    def tearDown(self):
        self.db.close()
        os.unlink(self.db_path)

    def _make_article(self, title="Test Article", source="Test Source",
                       category="jewelry", url="https://example.com/1"):
        return {
            "source_name": source,
            "source_url": "https://example.com",
            "title": title,
            "url": url,
            "published_date": "2024-01-15",
            "summary": "Test summary content",
            "category": category,
            "is_headline": False,
        }

    def test_save_single_article(self):
        articles = [self._make_article()]
        count = self.db.save_articles(self.session_id, articles)
        self.assertEqual(count, 1)

    def test_save_multiple_articles(self):
        articles = [
            self._make_article(title="Article 1", url="https://example.com/1"),
            self._make_article(title="Article 2", url="https://example.com/2"),
            self._make_article(title="Article 3", url="https://example.com/3"),
        ]
        count = self.db.save_articles(self.session_id, articles)
        self.assertEqual(count, 3)

    def test_get_latest_articles(self):
        articles_list = [
            self._make_article(title=f"Article {i}", url=f"https://example.com/{i}")
            for i in range(5)
        ]
        self.db.save_articles(self.session_id, articles_list)
        latest = self.db.get_latest_articles(limit=3)
        self.assertEqual(len(latest), 3)

    def test_get_articles_by_session(self):
        articles_list = [
            self._make_article(title=f"Session Article {i}", url=f"https://example.com/s{i}")
            for i in range(3)
        ]
        self.db.save_articles(self.session_id, articles_list)
        fetched = self.db.get_articles_by_session(self.session_id)
        self.assertEqual(len(fetched), 3)

    def test_get_articles_by_category(self):
        articles_list = [
            self._make_article(title="Jewelry Article", category="jewelry", url="https://example.com/j"),
            self._make_article(title="Etsy Article", category="etsy", url="https://example.com/e"),
            self._make_article(title="Commodity Article", category="commodity", url="https://example.com/c"),
        ]
        self.db.save_articles(self.session_id, articles_list)
        jewelry = self.db.get_articles_by_session(self.session_id, category="jewelry")
        self.assertEqual(len(jewelry), 1)
        self.assertEqual(jewelry[0].title, "Jewelry Article")


class TestCommodityPrices(unittest.TestCase):
    """Test commodity price storage and anomaly detection."""

    def setUp(self):
        from database import DatabaseManager
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        os.unlink(self.db_path)

    def test_save_commodity_prices(self):
        prices = [
            {"commodity": "gold", "price_usd": 2050.50, "unit": "oz"},
            {"commodity": "silver", "price_usd": 23.45, "unit": "oz"},
        ]
        self.db.save_commodity_prices(prices)
        latest = self.db.get_latest_commodity_prices()
        self.assertIn("gold", latest)
        self.assertIn("silver", latest)
        self.assertEqual(latest["gold"], 2050.50)

    def test_get_latest_commodity_prices_empty(self):
        latest = self.db.get_latest_commodity_prices()
        self.assertEqual(latest, {})

    def test_commodity_anomaly_score_insufficient_data(self):
        # Only one data point — no anomaly calculation possible
        prices = [{"commodity": "gold", "price_usd": 2000.00, "unit": "oz"}]
        self.db.save_commodity_prices(prices)
        score = self.db.get_commodity_anomaly_score("gold")
        self.assertEqual(score, 0.0)


class TestReports(unittest.TestCase):
    """Test report storage."""

    def setUp(self):
        from database import DatabaseManager
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.db = DatabaseManager(self.db_path)
        self.session_id = self.db.start_session(trigger="manual")

    def tearDown(self):
        self.db.close()
        os.unlink(self.db_path)

    def _create_report(self):
        self.db.save_report(
            session_id=self.session_id,
            report_date=date.today(),
            html_path="/tmp/test_report.html",
            pdf_path="/tmp/test_report.pdf",
            metadata={"total_articles": 10, "sources_succeeded": 3},
        )

    def test_save_report(self):
        self._create_report()
        reports = self.db.get_recent_reports(limit=10)
        self.assertEqual(len(reports), 1)

    def test_recent_reports_empty(self):
        reports = self.db.get_recent_reports(limit=5)
        self.assertEqual(len(reports), 0)

    def test_report_metadata(self):
        self._create_report()
        reports = self.db.get_recent_reports(limit=10)
        meta = reports[0].get_metadata()
        self.assertEqual(meta.get("total_articles"), 10)
        self.assertEqual(meta.get("sources_succeeded"), 3)


class TestDatabaseEdgeCases(unittest.TestCase):
    """Test edge cases in database operations."""

    def setUp(self):
        from database import DatabaseManager
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        os.unlink(self.db_path)

    def test_save_empty_articles(self):
        count = self.db.save_articles(1, [])
        self.assertEqual(count, 0)

    def test_get_stats_after_database_created(self):
        stats = self.db.get_stats()
        self.assertIsNotNone(stats)
        self.assertIn("total_articles", stats)

    def test_duplicate_articles_not_duplicated(self):
        sid = self.db.start_session(trigger="manual")
        article = {
            "source_name": "Test",
            "source_url": "https://example.com",
            "title": "Duplicate Title",
            "url": "https://example.com/dup",
            "published_date": "2024-01-15",
            "summary": "Test",
            "category": "jewelry",
            "is_headline": False,
        }
        self.db.save_articles(sid, [article])
        self.db.save_articles(sid, [article])  # Same article again
        articles = self.db.get_articles_by_session(sid)
        # Should be 1 (deduplicated), not 2
        self.assertEqual(len(articles), 1)


if __name__ == "__main__":
    unittest.main()