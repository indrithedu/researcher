# =============================================================================
# Tests: Report Generator
# =============================================================================

import os
import tempfile
from datetime import date

import pytest

from report_generator import ReportGenerator


class TestReportGenerator:
    """Test HTML report generation."""

    @pytest.fixture
    def temp_report_dir(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        import shutil
        shutil.rmtree(tmpdir)

    def test_init(self, sample_config):
        rg = ReportGenerator(sample_config)
        assert rg is not None

    def test_generate_html_creates_file(self, sample_config, temp_report_dir):
        """HTML report should be written to disk."""
        config = sample_config.copy()
        config["app"] = {"report_dir": temp_report_dir}

        rg = ReportGenerator(config)
        path = rg.generate_html(
            articles=[
                {"source_name": "Test", "title": "Test Article", "url": "https://example.com",
                 "published_date": "2024-12-01", "summary": "A test article", "category": "jewelry",
                 "is_headline": False, "source_url": "https://example.com"},
            ],
            headlines=[
                {"source_name": "Test", "title": "Top Headline", "url": "https://example.com/1",
                 "published_date": "2024-12-01", "summary": "A top headline", "category": "jewelry",
                 "is_headline": True, "source_url": "https://example.com"},
            ],
            etsy_intel=[
                {"source_name": "Etsy", "title": "Etsy Update", "url": "https://etsy.com",
                 "published_date": "2024-12-01", "summary": "An Etsy update", "category": "etsy",
                 "is_headline": False, "source_url": "https://etsy.com"},
            ],
            commodity_prices=[
                {"source_name": "Kitco - Gold", "title": "Gold Price: $2,345.50/oz",
                 "url": "https://kitco.com", "published_date": "2024-12-01", "summary": "Gold at $2,345.50",
                 "category": "commodity", "is_headline": False, "source_url": "https://kitco.com"},
            ],
            report_date=date(2024, 12, 1),
        )

        assert os.path.exists(path)
        assert "20241201" in path
        assert path.endswith(".html")

        # Check file has content
        with open(path) as f:
            content = f.read()
        assert len(content) > 500
        assert "JewelScope Research" in content
        assert "Top Headline" in content
        assert "Gold" in content

    def test_report_includes_disclaimer(self, sample_config, temp_report_dir):
        """Report footer should include the ToS disclaimer."""
        config = sample_config.copy()
        config["app"] = {"report_dir": temp_report_dir}

        rg = ReportGenerator(config)
        path = rg.generate_html(
            articles=[], headlines=[], etsy_intel=[], commodity_prices=[],
            report_date=date.today(),
        )

        with open(path) as f:
            content = f.read()

        assert "Terms of Service" in content or "robots.txt" in content

    def test_empty_report_graceful(self, sample_config, temp_report_dir):
        """Even with no data, the report should generate without crashing."""
        config = sample_config.copy()
        config["app"] = {"report_dir": temp_report_dir}

        rg = ReportGenerator(config)
        path = rg.generate_html(
            articles=[], headlines=[], etsy_intel=[], commodity_prices=[],
            report_date=date.today(),
        )

        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "No headlines" in content or "No commodity" in content

    def test_report_filename_format(self, sample_config, temp_report_dir):
        """Filename should follow the date-based convention."""
        config = sample_config.copy()
        config["app"] = {"report_dir": temp_report_dir}

        rg = ReportGenerator(config)
        path = rg.generate_html(
            articles=[], headlines=[], etsy_intel=[], commodity_prices=[],
            report_date=date(2024, 6, 15),
        )

        filename = os.path.basename(path)
        assert filename == "jewelscope_report_20240615.html"
