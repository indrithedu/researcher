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
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Date, Float, Boolean, JSON, ForeignKey, desc, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

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
    is_headline = Column(Boolean, default=False)

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
        self.Session = sessionmaker(bind=self.engine)
        logger.info(f"Database initialized: {db_path}")

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
        """Bulk-save articles from a scrape run."""
        with self.get_session() as db_session:
            for art in articles:
                a = Article(
                    session_id=session_id,
                    source_name=art.get("source_name", "unknown"),
                    source_url=art.get("source_url", ""),
                    title=art.get("title", "Untitled"),
                    url=art.get("url", ""),
                    published_date=art.get("published_date", ""),
                    summary=art.get("summary", ""),
                    category=art.get("category", ""),
                    is_headline=art.get("is_headline", False),
                )
                db_session.add(a)
            db_session.commit()
            logger.info(f"Saved {len(articles)} articles to session #{session_id}")

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
                    CommodityPrice.recorded_date >= date.today() - __import__('datetime').timedelta(days=days)
                )
                .order_by(CommodityPrice.recorded_date)
                .all()
            )

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