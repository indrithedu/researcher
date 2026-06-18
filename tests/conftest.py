# =============================================================================
# JewelScope Research — Test Configuration & Fixtures
# =============================================================================

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest
import yaml

# Ensure the project root is in the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Sample config for testing
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = {
    "app": {
        "name": "JewelScope Research Test",
        "version": "1.0.0",
        "data_dir": "./databases",
        "report_dir": "./reports",
    },
    "anti_detection": {
        "enabled": True,
        "request_delay_min": 0.01,
        "request_delay_max": 0.05,
        "max_retries": 1,
        "exponential_backoff_base": 1.5,
        "exponential_backoff_max": 5.0,
        "browser_engine": "playwright",
        "captcha": {"enabled": False, "service": "2captcha", "api_key": ""},
        "tls_fingerprint": "chrome120",
        "session_persistence": False,
        "session_dir": "/tmp/jewelscope_test_sessions",
        "proxies": ["", "http://test-proxy:8080"],
        "proxy_strategy": "random",
    },
    "sources": {
        "test_rss": {
            "name": "Test RSS",
            "url": "https://example.com/rss",
            "type": "rss",
            "enabled": True,
        },
        "test_article_list": {
            "name": "Test Article List",
            "url": "https://example.com/articles",
            "type": "article_list",
            "enabled": True,
            "selectors": {
                "article_container": "article",
                "title": "h2 a",
                "link": "h2 a",
                "date": "time",
                "summary": "p",
            },
        },
        "test_commodity": {
            "name": "Test Commodity",
            "url": "https://example.com/prices",
            "type": "commodity",
            "enabled": True,
        },
        "test_reddit": {
            "name": "Test Reddit",
            "url": "https://old.reddit.com/r/Test/",
            "type": "reddit",
            "enabled": True,
        },
        "test_disabled": {
            "name": "Test Disabled",
            "url": "https://example.com/disabled",
            "type": "article_list",
            "enabled": False,
        },
    },
    "scheduling": {"enabled": False, "cron": "0 7 * * *", "interval_hours": 24},
    "email": {"enabled": False},
}


@pytest.fixture
def sample_config():
    """Return a copy of the sample config."""
    import copy
    return copy.deepcopy(SAMPLE_CONFIG)


@pytest.fixture
def temp_config_file(sample_config):
    """Write sample config to a temp YAML file and return the path."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "config.yaml")
    with open(path, "w") as f:
        yaml.dump(sample_config, f)
    yield path
    shutil.rmtree(tmpdir)


@pytest.fixture
def temp_db_path():
    """Return a path for a temp SQLite database."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "test.db")
    yield path
    shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# Sample HTML snippets for scraper tests
# ---------------------------------------------------------------------------

SAMPLE_ARTICLE_HTML = """
<html>
<body>
    <article>
        <h2><a href="/article1">Record Diamond Sale at Sotheby's</a></h2>
        <time datetime="2024-12-01">December 1, 2024</time>
        <p>A rare blue diamond sold for record price at auction.</p>
    </article>
    <article>
        <h2><a href="/article2">Gold Prices Hit New High</a></h2>
        <time datetime="2024-12-02">December 2, 2024</time>
        <p>Gold reaches $2,400 per ounce amid economic uncertainty.</p>
    </article>
    <article>
        <h2><a href="/article3">Etsy Updates Seller Policies</a></h2>
        <time datetime="2024-12-03">December 3, 2024</time>
        <p>New fee structure announced for jewelry category sellers.</p>
    </article>
</body>
</html>
"""

SAMPLE_REDDIT_HTML = """
<html>
<body>
    <div class="thing">
        <a class="title" href="/r/EtsySellers/comments/abc/">Best jewelry listings this week</a>
        <time datetime="2024-12-01">2024-12-01</time>
        <div class="entry">
            <div class="usertext-body"><p>Here are my top performing listings...</p></div>
        </div>
    </div>
    <div class="thing stickied">
        <a class="title" href="/r/EtsySellers/comments/sticky/">Welcome to EtsySellers</a>
        <time datetime="2024-12-01">2024-12-01</time>
    </div>
    <div class="thing">
        <a class="title" href="/r/EtsySellers/comments/def/">Etsy algorithm change impact</a>
        <time datetime="2024-12-02">2024-12-02</time>
    </div>
</body>
</html>
"""

SAMPLE_COMMODITY_HTML = """
<html>
<body>
    <table class="price-table">
        <tr><td>Gold</td><td>$2,345.50</td></tr>
        <tr><td>Silver</td><td>$28.75</td></tr>
        <tr><td>Platinum</td><td>$945.20</td></tr>
        <tr><td>Palladium</td><td>$1,025.00</td></tr>
    </table>
</body>
</html>
"""

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>Jewelry News</title>
    <item>
        <title>Diamond Market Update December 2024</title>
        <link>https://example.com/diamond-dec-2024</link>
        <pubDate>Mon, 02 Dec 2024 10:00:00 GMT</pubDate>
        <description>Latest trends in the diamond market show increased demand for lab-grown stones.</description>
    </item>
    <item>
        <title>Etsy Holiday Shopping Trends</title>
        <link>https://example.com/etsy-holiday-2024</link>
        <pubDate>Sun, 01 Dec 2024 08:30:00 GMT</pubDate>
        <description>Handmade jewelry tops Etsy holiday search trends this year.</description>
    </item>
</channel>
</rss>
"""


@pytest.fixture
def sample_article_html():
    return SAMPLE_ARTICLE_HTML


@pytest.fixture
def sample_reddit_html():
    return SAMPLE_REDDIT_HTML


@pytest.fixture
def sample_commodity_html():
    return SAMPLE_COMMODITY_HTML


@pytest.fixture
def sample_rss_xml():
    return SAMPLE_RSS_XML
