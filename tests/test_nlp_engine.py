"""
E2E tests for the NLP engine — no API keys needed.
Tests: sentiment analysis, keyword extraction, summarization, article clustering.
"""

import unittest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestNLPSentiment(unittest.TestCase):
    """Test VADER sentiment analysis on jewelry-related text."""

    @classmethod
    def setUpClass(cls):
        from utils.nlp_engine import NLPEngine
        cls.nlp = NLPEngine()

    def test_positive_sentiment(self):
        result = self.nlp.analyze_sentiment(
            "This gorgeous diamond ring is absolutely stunning and beautiful!"
        )
        self.assertIn("score", result)
        self.assertIn("label", result)
        self.assertGreater(result["score"], 0.3)
        self.assertEqual(result["label"], "Positive")

    def test_negative_sentiment(self):
        result = self.nlp.analyze_sentiment(
            "Terrible quality, the gold plating chipped off after one day."
        )
        self.assertLess(result["score"], -0.1)
        self.assertEqual(result["label"], "Negative")

    def test_neutral_sentiment(self):
        result = self.nlp.analyze_sentiment(
            "The ring is made of 14k gold and weighs 3.2 grams."
        )
        self.assertGreaterEqual(result["label"], "Neutral")

    def test_empty_text(self):
        result = self.nlp.analyze_sentiment("")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["label"], "Neutral")

    def test_mixed_sentiment(self):
        result = self.nlp.analyze_sentiment(
            "Beautiful design but the price is way too high for what you get."
        )
        # Should be mixed — VADER will still classify
        self.assertIn("score", result)
        self.assertIn("label", result)


class TestNLPKeywords(unittest.TestCase):
    """Test RAKE keyword extraction."""

    @classmethod
    def setUpClass(cls):
        from utils.nlp_engine import NLPEngine
        cls.nlp = NLPEngine()

    def test_extract_keywords_jewelry(self):
        text = (
            "This 18k gold diamond engagement ring features a brilliant cut "
            "center stone with pave set side diamonds. The band is made of "
            "solid gold and comes with a certificate of authenticity."
        )
        keywords = self.nlp.extract_keywords(text)
        self.assertIsInstance(keywords, list)
        self.assertGreater(len(keywords), 0)
        # Check for jewelry-relevant keywords
        all_text = " ".join(keywords).lower()
        self.assertTrue(
            any(kw in all_text for kw in ["gold", "diamond", "ring", "engagement"]),
            f"Expected jewelry keywords in: {keywords}"
        )

    def test_extract_keywords_short_text(self):
        keywords = self.nlp.extract_keywords("Gold necklace")
        self.assertIsInstance(keywords, list)
        self.assertGreater(len(keywords), 0)

    def test_extract_keywords_empty(self):
        keywords = self.nlp.extract_keywords("")
        self.assertEqual(keywords, [])


class TestNLPSummarization(unittest.TestCase):
    """Test LexRank extractive summarization."""

    @classmethod
    def setUpClass(cls):
        from utils.nlp_engine import NLPEngine
        cls.nlp = NLPEngine()

    def test_summarize_article(self):
        text = (
            "The global diamond market is experiencing a shift as lab-grown "
            "diamonds gain popularity among younger consumers. Traditional "
            "diamond miners are facing pressure to differentiate their products. "
            "Meanwhile, retailers are expanding their lab-grown offerings. "
            "Consumer demand for ethically sourced gems continues to rise. "
            "The price gap between natural and lab-grown diamonds is widening. "
            "Industry analysts predict this trend will continue through 2025."
        )
        summary = self.nlp.summarize(text)
        self.assertIsInstance(summary, str)
        self.assertGreater(len(summary), 0)

    def test_summarize_short_text(self):
        text = "Gold prices are up 5% this week."
        summary = self.nlp.summarize(text)
        # Short text should return as-is or similar
        self.assertIsInstance(summary, str)


class TestNLPClustering(unittest.TestCase):
    """Test article clustering."""

    @classmethod
    def setUpClass(cls):
        from utils.nlp_engine import NLPEngine
        cls.nlp = NLPEngine()

    def test_cluster_similar_articles(self):
        articles = [
            {"title": "Gold prices hit new high this quarter", "summary": "Gold rally continues"},
            {"title": "Gold market sees record demand", "summary": "Investors flock to gold"},
            {"title": "Diamond engagement rings trending", "summary": "Solitaire settings popular"},
        ]
        clusters = self.nlp.cluster_articles(articles)
        self.assertIsInstance(clusters, dict)
        # At least one cluster
        self.assertGreater(len(clusters), 0)

    def test_cluster_empty(self):
        clusters = self.nlp.cluster_articles([])
        self.assertEqual(clusters, {})


if __name__ == "__main__":
    unittest.main()