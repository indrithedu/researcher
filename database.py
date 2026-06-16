# =============================================================================
# JewelScope Research — Database Module
# =============================================================================
# Handles all SQLite operations: schema creation, report storage,
# source config persistence, and historical data retrieval.
#
# Uses SQLAlchemy ORM for clean, type-safe database interactions.
# =============================================================================

import os
import json
import logging
import re
import statistics
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Date, Float, Boolean, JSON, ForeignKey, desc, func, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datasketch import MinHash

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

Base = declarative_base()


class ScrapeSession(Base):
    """Records each scraping run (scheduled or manual)."""
    __tablename__ = "scrape_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")  # running, success, partial, failed
    sources_attempted = Column(Integer, default=0)
    sources_succeeded = Column(Integer, default=0)
    sources_failed = Column(Integer, default=0)
    total_articles_found = Column(Integer, default=0)
    trigger = Column(String(20), default="manual")  # manual, scheduled
    error_log = Column(Text, nullable=True)          # JSON list of errors

    # Relationship
    articles = relationship("Article", back_populates="session", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="session", cascade="all, delete-orphan")

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class Article(Base):
    """Individual article found during a scrape session."""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("scrape_sessions.id"), nullable=False)
    source_name = Column(String(100), nullable=False)
    source_url = Column(String(500), nullable=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    published_date = Column(String(100), nullable=True)  # original date string
    parsed_date = Column(Date, nullable=True)             # parsed date
    summary = Column(Text, nullable=True)
    content_snippet = Column(Text, nullable=True)         # first ~300 chars
    category = Column(String(50), nullable=True)          # jewelry, etsy, commodity, fashion
    sentiment = Column(String(20), nullable=True)         # positive, negative, neutral
    sentiment_score = Column(Float, nullable=True)        # -1.0 to 1.0
    keywords = Column(JSON, nullable=True)                # JSON list of keywords
    entities = Column(JSON, nullable=True)                # JSON list of extracted brands/orgs
    dominant_colors = Column(JSON, nullable=True)         # JSON list of hex strings
    sparkle_score = Column(Float, nullable=True)          # 0.0 to 1.0
    jewelry_type = Column(String(50), nullable=True)      # ring, necklace, etc.
    is_headline = Column(Boolean, default=False)
    image_hash = Column(String(64), nullable=True)            # dHash for image deduplication
    content_hash = Column(Text, nullable=True)            # MinHash or simple hash

    session = relationship("ScrapeSession", back_populates="articles")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "published_date": self.published_date,
            "summary": self.summary,
            "category": self.category,
            "is_headline": self.is_headline,
        }


class CommodityPrice(Base):
    """Daily commodity price snapshot."""
    __tablename__ = "commodity_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recorded_date = Column(Date, default=date.today, nullable=False)
    commodity = Column(String(50), nullable=False)    # gold, silver, platinum, diamond
    price_usd = Column(Float, nullable=False)
    unit = Column(String(20), default="oz")           # oz, gram, carat
    change_pct = Column(Float, nullable=True)          # 24h change %
    source = Column(String(100), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    """Generated daily report."""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("scrape_sessions.id"), nullable=False)
    report_date = Column(Date, default=date.today, nullable=False)
    report_type = Column(String(20), default="daily")    # daily, weekly, manual
    html_path = Column(String(500), nullable=True)        # path to saved HTML
    pdf_path = Column(String(500), nullable=True)         # path to saved PDF
    email_sent = Column(Boolean, default=False)
    email_recipients = Column(Text, nullable=True)        # JSON list
    created_at = Column(DateTime, default=datetime.utcnow)
    report_metadata = Column(Text, nullable=True)         # JSON with summary

    session = relationship("ScrapeSession", back_populates="reports")

    def get_metadata(self) -> Dict[str, Any]:
        if self.report_metadata:
            return json.loads(self.report_metadata)
        return {}

    def set_metadata(self, data: Dict[str, Any]):
        self.report_metadata = json.dumps(data)


# ---------------------------------------------------------------------------
# Database Manager
# ---------------------------------------------------------------------------

class DatabaseManager:
    """Manages the SQLite database — schema, CRUD, and queries."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self._init_fts()
        self.Session = sessionmaker(bind=self.engine)
        logger.info(f"Database initialized: {db_path}")

    def _init_fts(self):
        """Initialize FTS5 virtual table for full-text search."""
        with self.engine.connect() as conn:
            conn.execute(text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5("
                "id UNINDEXED, title, summary"
                ");"
            ))
            conn.commit()

    def _get_minhash(self, text_content: str) -> MinHash:
        """Generate MinHash for a string of text."""
        mh = MinHash(num_perm=128)
        # Tokenize by words (simple)
        words = set(re.findall(r"\w+", text_content.lower()))
        for word in words:
            mh.update(word.encode('utf8'))
        return mh

    def _is_near_duplicate(self, db_session, new_mh: MinHash, threshold: float = 0.8) -> bool:
        """Check if a near-duplicate exists in the last 7 days."""
        seven_days_ago = date.today() - timedelta(days=7)
        recent_articles = (
            db_session.query(Article.content_hash)
            .join(ScrapeSession)
            .filter(func.date(ScrapeSession.started_at) >= seven_days_ago)
            .all()
        )

        for (stored_hash_json,) in recent_articles:
            if not stored_hash_json:
                continue
            try:
                # content_hash stores the MinHash values as JSON list
                stored_values = json.loads(stored_hash_json)
                stored_mh = MinHash(num_perm=128, hashvalues=stored_values)
                if new_mh.jaccard(stored_mh) >= threshold:
                    return True
            except Exception as e:
                logger.warning(f"Error comparing MinHash: {e}")
                continue
        return False

    def get_session(self):
        """Get a new SQLAlchemy session (use as context manager)."""
        return self.Session()

    # -----------------------------------------------------------------------
    # Scrape Sessions
    # -----------------------------------------------------------------------

    def start_session(self, trigger: str = "manual") -> int:
        """Create a new scrape session and return its ID."""
        with self.get_session() as session:
            ss = ScrapeSession(trigger=trigger)
            session.add(ss)
            session.commit()
            logger.info(f"Started scrape session #{ss.id} ({trigger})")
            return ss.id

    def complete_session(self, session_id: int, status: str,
                         succeeded: int = 0, failed: int = 0,
                         articles: int = 0, errors: list = None):
        """Mark a session as completed with results."""
        with self.get_session() as session:
            ss = session.query(ScrapeSession).filter_by(id=session_id).first()
            if ss:
                ss.completed_at = datetime.utcnow()
                ss.status = status
                ss.sources_attempted = succeeded + failed
                ss.sources_succeeded = succeeded
                ss.sources_failed = failed
                ss.total_articles_found = articles
                if errors:
                    ss.error_log = json.dumps(errors[:50])  # cap at 50 errors
                session.commit()
                logger.info(f"Session #{session_id} completed: {status} "
                            f"({succeeded} OK, {failed} failed, {articles} articles)")

    def get_recent_sessions(self, limit: int = 10) -> List[ScrapeSession]:
        """Get most recent scrape sessions."""
        with self.get_session() as session:
            return (
                session.query(ScrapeSession)
                .order_by(desc(ScrapeSession.started_at))
                .limit(limit)
                .all()
            )

    # -----------------------------------------------------------------------
    # Articles
    # -----------------------------------------------------------------------

    def save_articles(self, session_id: int, articles: List[Dict[str, Any]]):
        """Bulk-save articles from a scrape run with deduplication."""
        saved_count = 0
        with self.get_session() as db_session:
            for art in articles:
                title = art.get("title", "Untitled")
                summary = art.get("summary", "")
                content_for_hash = f"{title} {summary}"
                
                new_mh = self._get_minhash(content_for_hash)
                
                if self._is_near_duplicate(db_session, new_mh):
                    logger.info(f"Skipping duplicate: {title[:50]}...")
                    continue

                a = Article(
                    session_id=session_id,
                    source_name=art.get("source_name", "unknown"),
                    source_url=art.get("source_url", ""),
                    title=title,
                    url=art.get("url", ""),
                    published_date=art.get("published_date", ""),
                    summary=summary,
                    category=art.get("category", ""),
                    sentiment=art.get("sentiment", ""),
                    sentiment_score=art.get("sentiment_score", 0.0),
                    keywords=art.get("keywords", []),
                    entities=art.get("entities", []),
                    dominant_colors=art.get("dominant_colors", []),
                    sparkle_score=art.get("sparkle_score", 0.0),
                    jewelry_type=art.get("jewelry_type", ""),
                    is_headline=art.get("is_headline", False),
                    image_hash=art.get("image_hash", None),
                    content_hash=json.dumps(new_mh.hashvalues.tolist())
                )
                db_session.add(a)
                db_session.flush()  # To get the ID for FTS
                
                # Sync to FTS
                db_session.execute(text(
                    "INSERT INTO articles_fts (id, title, summary) VALUES (:id, :title, :summary)"
                ), {"id": a.id, "title": title, "summary": summary})
                
                saved_count += 1
            
            db_session.commit()
            logger.info(f"Saved {saved_count} new articles to session #{session_id} (Deduplicated)")

    def search_articles(self, query: str, limit: int = 50) -> List[Article]:
        """Search articles using Full-Text Search (FTS5)."""
        with self.get_session() as session:
            # Query FTS table to get IDs
            # Note: query should follow FTS5 syntax or be sanitized
            results = session.execute(text(
                "SELECT id FROM articles_fts WHERE articles_fts MATCH :query ORDER BY rank LIMIT :limit"
            ), {"query": query, "limit": limit}).fetchall()
            
            ids = [r[0] for r in results]
            if not ids:
                return []
            
            # Fetch full objects
            articles = (
                session.query(Article)
                .filter(Article.id.in_(ids))
                .all()
            )
            # Re-sort to match FTS ranking
            article_map = {a.id: a for a in articles}
            return [article_map[aid] for aid in ids if aid in article_map]

    def get_articles_by_session(self, session_id: int) -> List[Article]:
        """Get all articles for a given session."""
        with self.get_session() as session:
            return (
                session.query(Article)
                .filter_by(session_id=session_id)
                .order_by(desc(Article.is_headline), Article.id)
                .all()
            )

    def get_headlines_by_date(self, report_date: date) -> List[Article]:
        """Get headlines for a specific date across all sessions."""
        with self.get_session() as session:
            return (
                session.query(Article)
                .join(ScrapeSession)
                .filter(
                    func.date(ScrapeSession.started_at) == report_date,
                    Article.is_headline == True
                )
                .order_by(Article.id)
                .all()
            )

    def get_latest_articles(self, limit: int = 50) -> List[Article]:
        """Get the most recent articles across all sessions."""
        with self.get_session() as session:
            return (
                session.query(Article)
                .order_by(desc(Article.id))
                .limit(limit)
                .all()
            )

    # -----------------------------------------------------------------------
    # Commodity Prices
    # -----------------------------------------------------------------------

    def save_commodity_prices(self, prices: List[Dict[str, Any]]):
        """Save commodity price snapshots."""
        with self.get_session() as session:
            for price in prices:
                cp = CommodityPrice(
                    commodity=price.get("commodity", ""),
                    price_usd=price.get("price_usd", 0.0),
                    unit=price.get("unit", "oz"),
                    change_pct=price.get("change_pct"),
                    source=price.get("source", ""),
                )
                session.add(cp)
            session.commit()
            logger.info(f"Saved {len(prices)} commodity prices")

    def get_latest_commodity_prices(self) -> Dict[str, float]:
        """Get the most recent price for each commodity."""
        with self.get_session() as session:
            # Subquery: max id per commodity
            subq = (
                session.query(
                    CommodityPrice.commodity,
                    func.max(CommodityPrice.id).label("max_id")
                )
                .group_by(CommodityPrice.commodity)
                .subquery()
            )
            results = (
                session.query(CommodityPrice)
                .join(subq, CommodityPrice.id == subq.c.max_id)
                .all()
            )
            return {r.commodity: r.price_usd for r in results}

    def get_price_history(self, commodity: str, days: int = 30) -> List[CommodityPrice]:
        """Get price history for a commodity."""
        with self.get_session() as session:
            return (
                session.query(CommodityPrice)
                .filter(
                    CommodityPrice.commodity == commodity,
                    CommodityPrice.recorded_date >= date.today() - timedelta(days=days)
                )
                .order_by(CommodityPrice.recorded_date)
                .all()
            )

    def get_commodity_anomaly_score(self, commodity: str) -> float:
        """
        Calculate the Z-score for the latest price of a commodity.
        Z = (Latest - Mean) / StdDev
        Returns 0.0 if not enough data points (< 5).
        """
        history = self.get_price_history(commodity, days=30)
        if len(history) < 5:
            return 0.0

        prices = [p.price_usd for p in history]
        latest = prices[-1]
        
        try:
            mean = statistics.mean(prices)
            stdev = statistics.stdev(prices)
            if stdev == 0:
                return 0.0
            return (latest - mean) / stdev
        except statistics.StatisticsError:
            return 0.0

    # -----------------------------------------------------------------------
    # Reports
    # -----------------------------------------------------------------------

    def save_report(self, session_id: int, report_date: date,
                    html_path: str = None, pdf_path: str = None,
                    metadata: dict = None) -> int:
        """Save a report record."""
        with self.get_session() as session:
            r = Report(
                session_id=session_id,
                report_date=report_date,
                html_path=html_path,
                pdf_path=pdf_path,
            )
            if metadata:
                r.set_metadata(metadata)
            session.add(r)
            session.commit()
            return r.id

    def get_recent_reports(self, limit: int = 30) -> List[Report]:
        """Get most recent reports."""
        with self.get_session() as session:
            return (
                session.query(Report)
                .order_by(desc(Report.report_date))
                .limit(limit)
                .all()
            )

    def get_report_by_date(self, report_date: date) -> Optional[Report]:
        """Get a report by date."""
        with self.get_session() as session:
            return (
                session.query(Report)
                .filter_by(report_date=report_date)
                .order_by(desc(Report.id))
                .first()
            )

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_session() as session:
            return {
                "total_sessions": session.query(func.count(ScrapeSession.id)).scalar(),
                "total_articles": session.query(func.count(Article.id)).scalar(),
                "total_reports": session.query(func.count(Report.id)).scalar(),
                "total_commodity_prices": session.query(func.count(CommodityPrice.id)).scalar(),
                "sources_with_data": (
                    session.query(Article.source_name)
                    .distinct()
                    .count()
                ),
                "latest_session": (
                    session.query(ScrapeSession)
                    .order_by(desc(ScrapeSession.started_at))
                    .first()
                ),
            }

    # -----------------------------------------------------------------------
    # Trend Analysis
    # -----------------------------------------------------------------------

    def get_keyword_momentum(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Calculate momentum for keywords over two consecutive periods.
        Momentum = (CurrentFreq - PreviousFreq) / max(1, PreviousFreq)
        """
        current_end = datetime.utcnow()
        current_start = current_end - timedelta(days=days)
        previous_end = current_start
        previous_start = previous_end - timedelta(days=days)

        def _get_freqs(start_dt, end_dt):
            with self.get_session() as session:
                articles = (
                    session.query(Article.keywords)
                    .join(ScrapeSession)
                    .filter(ScrapeSession.started_at >= start_dt, ScrapeSession.started_at < end_dt)
                    .all()
                )
                freqs = {}
                for (keywords_json,) in articles:
                    if not keywords_json:
                        continue
                    try:
                        # SQLAlchemy handles JSON serialization, but let's be safe
                        keywords = keywords_json if isinstance(keywords_json, list) else json.loads(keywords_json)
                        for k in keywords:
                            if isinstance(k, str):
                                k = k.lower().strip()
                                if k:
                                    freqs[k] = freqs.get(k, 0) + 1
                    except Exception as e:
                        logger.warning(f"Error parsing keywords JSON: {e}")
                        continue
                return freqs

        current_freqs = _get_freqs(current_start, current_end)
        previous_freqs = _get_freqs(previous_start, previous_end)

        momentum_data = []
        all_keywords = set(current_freqs.keys()) | set(previous_freqs.keys())

        for k in all_keywords:
            c = current_freqs.get(k, 0)
            p = previous_freqs.get(k, 0)
            # Simple momentum calculation
            momentum = (c - p) / max(1, p)
            momentum_data.append({
                "keyword": k,
                "count": c,
                "previous_count": p,
                "momentum": momentum
            })

        # Sort by momentum descending, then current count descending
        momentum_data.sort(key=lambda x: (x["momentum"], x["count"]), reverse=True)
        return momentum_data
