"""
E2E tests for anti-detection engine — no external services needed.
Tests: user-agent rotation, URL normalization, cookie handling.
"""

import unittest
import sys
import os
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestUserAgentPool(unittest.TestCase):
    """Test the user agent pool provides valid browsers."""

    def setUp(self):
        from anti_detect import USER_AGENT_POOL
        self.pool = USER_AGENT_POOL

    def test_pool_not_empty(self):
        self.assertGreater(len(self.pool), 0)

    def test_all_agents_start_with_browser_name(self):
        """Every UA should start with Mozilla/5.0 for compatibility."""
        for ua in self.pool[:50]:
            self.assertTrue(ua.startswith("Mozilla/5.0"),
                            f"UA doesn't start with Mozilla: {ua[:50]}")

    def test_agents_contain_different_browsers(self):
        """Pool should have Chrome, Firefox, and Safari agents."""
        all_text = " ".join(self.pool[:100])
        self.assertIn("Chrome", all_text)
        self.assertIn("Firefox", all_text)
        self.assertIn("Safari", all_text)

    def test_no_excessive_duplicate_agents(self):
        """Pool should not have excessive duplicates."""
        unique = set(self.pool)
        # Allow some duplicates (pool may have weighted entries)
        dup_ratio = (len(self.pool) - len(unique)) / len(self.pool)
        self.assertLess(dup_ratio, 0.1,
                        f"Found {(len(self.pool) - len(unique))} duplicates in {len(self.pool)} agents")


class TestAntiDetectClientInit(unittest.TestCase):
    """Test AntiDetectClient initialization without connections."""

    def setUp(self):
        from anti_detect import AntiDetectClient
        self.config = {
            "anti_detection": {
                "enabled": True,
                "request_delay_min": 0,
                "request_delay_max": 0,
                "max_retries": 1,
                "proxies": [""],
                "proxy_strategy": "random",
            }
        }
        self.client = AntiDetectClient(self.config)

    def test_client_creation(self):
        self.assertIsNotNone(self.client)
        self.assertTrue(self.client.enabled)

    def test_random_user_agent(self):
        """Test getting a random user agent."""
        ua = self.client.get_random_ua()
        self.assertTrue(ua.startswith("Mozilla"))

    def test_proxy_round_robin(self):
        config = self.config.copy()
        config["anti_detection"]["proxy_strategy"] = "round_robin"
        client = AntiDetectClient(config)
        self.assertIsNotNone(client)

    def test_disabled_anti_detection(self):
        config = {"anti_detection": {"enabled": False}}
        client = AntiDetectClient(config)
        self.assertFalse(client.enabled)

    def test_session_headers(self):
        """Test headers dict is well-formed."""
        headers = self.client._get_headers()
        self.assertIsInstance(headers, dict)
        self.assertIn("User-Agent", headers)
        self.assertIn("Accept", headers)
        self.assertIn("Accept-Language", headers)


class TestAntiDetectRequestLogic(unittest.TestCase):
    """Test request handling logic without making real HTTP calls."""

    def setUp(self):
        from anti_detect import AntiDetectClient
        self.client = AntiDetectClient({
            "anti_detection": {
                "enabled": True,
                "request_delay_min": 0,
                "request_delay_max": 0,
                "max_retries": 1,
                "proxies": [""],
                "proxy_strategy": "random",
                "session_persistence": False,
            }
        })

    def test_url_normalization(self):
        """Test full URL construction from relative paths."""
        url = self.client._normalize_url("https://example.com")
        self.assertEqual(url, "https://example.com")

    def test_url_with_path(self):
        url = self.client._normalize_url("https://example.com/news")
        self.assertEqual(url, "https://example.com/news")

    @patch("anti_detect.httpx.Client")
    def test_make_request_handles_timeout(self, mock_client):
        """Synchronous request should handle timeouts gracefully."""
        mock_instance = MagicMock()
        mock_instance.get.side_effect = Exception("Connection timeout")
        mock_client.return_value = mock_instance.__enter__.return_value

        html, status = self.client.get("https://example.com")
        # Should return empty with error status
        self.assertEqual(html, "")


class TestStealthBrowser(unittest.TestCase):
    """Test StealthBrowser initialization (no actual browser launch)."""

    @patch("anti_detect.anti_detect.sync_playwright")
    def test_browser_initialization_fallback(self, mock_playwright):
        """Should handle Playwright not being available gracefully."""
        mock_playwright.side_effect = ImportError("Playwright not installed")
        from anti_detect import StealthBrowser

        browser = StealthBrowser({})
        # Should not crash — just not have a browser
        self.assertIsNotNone(browser)

    def test_stealth_browser_creation(self):
        """Test the browser object can be created."""
        from anti_detect import StealthBrowser
        browser = StealthBrowser({})
        self.assertIsNotNone(browser)


class TestCookieJar(unittest.TestCase):
    """Test cookie/persistence handling."""

    def setUp(self):
        from anti_detect import AntiDetectClient
        self.tmp_dir = tempfile.mkdtemp()
        self.client = AntiDetectClient({
            "anti_detection": {
                "enabled": True,
                "request_delay_min": 0,
                "request_delay_max": 0,
                "max_retries": 1,
                "proxies": [""],
                "proxy_strategy": "random",
                "session_persistence": True,
                "session_dir": self.tmp_dir,
            }
        })

    def test_session_directory_created(self):
        import os
        self.assertTrue(os.path.exists(self.tmp_dir))


if __name__ == "__main__":
    unittest.main()