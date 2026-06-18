# =============================================================================
# Tests: Configuration Loading & Scheduler
# =============================================================================

import os
import yaml


class TestConfig:
    """Test that the real config file loads and has required fields."""

    def test_config_exists(self):
        """The config.yaml file must be present."""
        assert os.path.exists("config.yaml")

    def test_config_loads(self):
        """Config should parse as valid YAML."""
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        assert config is not None

    def test_config_has_required_sections(self):
        """Config should have all major sections."""
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        assert "app" in config
        assert "anti_detection" in config
        assert "sources" in config
        assert "scheduling" in config

    def test_config_has_sources(self):
        """Config should list news sources."""
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        sources = config.get("sources", {})
        assert len(sources) >= 5  # At least 5 sources

    def test_each_source_has_required_fields(self):
        """Every source should have name, url, type, enabled."""
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        for name, source in config.get("sources", {}).items():
            assert "name" in source, f"Source {name} missing 'name'"
            assert "url" in source, f"Source {name} missing 'url'"
            assert "type" in source, f"Source {name} missing 'type'"
            assert "enabled" in source, f"Source {name} missing 'enabled'"

    def test_google_news_sources_present(self):
        """At least one Google News RSS source should be configured."""
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        google_sources = [
            name for name, src in config.get("sources", {}).items()
            if "google" in name.lower()
        ]
        assert len(google_sources) >= 1

    def test_etsy_sources_present(self):
        """At least one Etsy-related source should be configured."""
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        etsy_sources = [
            name for name, src in config.get("sources", {}).items()
            if "etsy" in name.lower()
        ]
        assert len(etsy_sources) >= 1


class TestScheduler:
    """Test scheduler initialization."""

    def test_scheduler_imports(self):
        """Scheduler module should import cleanly."""
        import importlib
        import scheduler
        importlib.reload(scheduler)
        assert True

    def test_scheduler_init(self, sample_config):
        """Scheduler should initialize with a callback."""
        from scheduler import ResearchScheduler

        def dummy_callback():
            pass

        sched = ResearchScheduler(sample_config, dummy_callback)
        assert sched.enabled is False  # We set enabled: false in test config
        assert sched.cron == "0 7 * * *"