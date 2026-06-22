# =============================================================================
# JewelScope Research — Report Generator
# =============================================================================
# Generates beautiful daily HTML reports and optionally converts to PDF.
# Reports include headlines, market trends, Etsy intelligence, commodity
# prices, and a quick-scan table.
# =============================================================================

import os
import json
import logging
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from utils.nlp_engine import NLPEngine

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates HTML and PDF reports from scraped content."""

    def __init__(self, config: dict):
        self.config = config
        self.report_dir = config.get("app", {}).get("report_dir", "./reports")
        os.makedirs(self.report_dir, exist_ok=True)
        self.nlp = NLPEngine()

    def generate_html(self, articles: List[Dict[str, Any]],
                      headlines: List[Dict[str, Any]],
                      etsy_intel: List[Dict[str, Any]],
                      commodity_prices: List[Dict[str, Any]],
                      session_summary: dict = None,
                      fine_jewelry_insights: dict = None,
                      google_trends_report: object = None,
                      pinterest_report: object = None,
                      report_date: date = None) -> str:
        """
        Generate a complete HTML report.
        Args:
            fine_jewelry_insights: Optional dict from FineJewelryAnalyzer.analyze()
            google_trends_report: Optional TrendsOverlayReport from Google Trends
            pinterest_report: Optional PinterestTrendReport from Pinterest scraper
        Returns: path to the generated HTML file.
        """
        report_date = report_date or date.today()
        html_content = self._build_html(
            articles=articles,
            headlines=headlines,
            etsy_intel=etsy_intel,
            commodity_prices=commodity_prices,
            session_summary=session_summary or {},
            fine_jewelry_insights=fine_jewelry_insights,
            google_trends_report=google_trends_report,
            pinterest_report=pinterest_report,
            report_date=report_date,
        )

        # Save to file
        filename = f"jewelscope_report_{report_date.strftime('%Y%m%d')}.html"
        filepath = os.path.join(self.report_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"HTML report saved: {filepath}")
        return filepath

    def _build_html(self, articles, headlines, etsy_intel, commodity_prices,
                    session_summary, fine_jewelry_insights=None,
                    google_trends_report=None,
                    pinterest_report=None,
                    report_date=None) -> str:
        """Build the full HTML document."""

        # Format commodity prices nicely
        commodity_rows = ""
        if commodity_prices:
            for cp in commodity_prices:
                title = cp.get("title", "")
                summary = cp.get("summary", "")
                commodity_rows += f"""
                <tr>
                    <td class="commodity-name">
                        <span class="metal-dot"></span>
                        {title.split("Price:")[0] if "Price:" in title else title}
                    </td>
                    <td class="commodity-price">{title.split("$")[-1] if "$" in title else "—"}</td>
                    <td class="commodity-source">{summary[:80]}</td>
                </tr>"""
        if not commodity_rows:
            commodity_rows = "<tr><td colspan='3' class='empty'>No commodity data fetched</td></tr>"

        # Build headlines (Clustered)
        headline_items = ""
        if headlines:
            from collections import Counter
            clusters = self.nlp.cluster_articles(headlines)
            
            for cluster_id, cluster_articles in clusters.items():
                # Represent cluster with the first article's title
                representative = cluster_articles[0]
                cluster_title = representative.get("title", f"Cluster {cluster_id}")
                
                # Get common keywords for the cluster header
                all_keywords = []
                for art in cluster_articles:
                    all_keywords.extend(art.get("keywords", []))
                top_k = [k for k, count in Counter(all_keywords).most_common(3)]
                keyword_str = f" | {', '.join(top_k)}" if top_k else ""

                headline_items += f"""
                <div class="cluster-header">
                    <span class="cluster-icon">📂</span> Topic: {cluster_title[:80]}{"..." if len(cluster_title) > 80 else ""} {keyword_str}
                </div>"""

                for i, h in enumerate(cluster_articles, 1):
                    url = h.get("url", "")
                    title = h.get("title", "Untitled")
                    source = h.get("source_name", "")
                    pub_date = h.get("published_date", "")
                    summary = h.get("summary", "")
                    image_url = h.get("image_url", "")
                    
                    # NLP data
                    sentiment = h.get("sentiment", "Neutral")
                    sentiment_score = h.get("sentiment_score", 0.0)
                    keywords = h.get("keywords", [])
                    
                    # Vision data
                    colors = h.get("dominant_colors", [])
                    sparkle = h.get("sparkle_score", 0.0)
                    j_type = h.get("jewelry_type", "")

                    sentiment_class = sentiment.lower()
                    keyword_tags = "".join([f'<span class="keyword-tag">{k}</span>' for k in keywords[:5]])
                    
                    color_swatches = "".join([f'<div class="color-swatch" style="background:{c};"></div>' for k, c in enumerate(colors)])
                    
                    vision_meta = ""
                    if j_type or sparkle > 0 or colors:
                        vision_meta = f"""
                        <div class="vision-meta">
                            {f'<span class="jewelry-badge">{j_type}</span>' if j_type else ''}
                            {f'<span class="sparkle-badge">Sparkle: {int(sparkle*100)}%</span>' if sparkle > 0 else ''}
                            <div class="color-palette">{color_swatches}</div>
                        </div>"""

                    link_tag = f'<a href="{url}" target="_blank">{title}</a>' if url else title
                    
                    image_html = f'<div class="headline-image"><img src="{image_url}" alt="Article Image"></div>' if image_url else ''
                    
                    headline_items += f"""
                    <div class="headline-item {sentiment_class}">
                        <div class="headline-number">{i}.</div>
                        {image_html}
                        <div class="headline-content">
                            <div class="headline-title">{link_tag}</div>
                            <div class="headline-meta">
                                <span class="headline-source">{source}</span>
                                {f'<span class="headline-date">{pub_date}</span>' if pub_date else ''}
                                <span class="sentiment-badge {sentiment_class}">{sentiment} ({sentiment_score:+.2f})</span>
                            </div>
                            {f'<div class="headline-summary">{summary}</div>' if summary else ''}
                            <div class="headline-keywords">{keyword_tags}</div>
                            {vision_meta}
                        </div>
                    </div>"""

        if not headline_items:
            headline_items = "<div class='empty-state'>No headlines captured in this run. Check your source config.</div>"

        # Build Etsy intelligence
        etsy_items = ""
        for e in etsy_intel[:8]:
            url = e.get("url", "")
            title = e.get("title", "Untitled")
            source = e.get("source_name", "")
            summary = e.get("summary", "")
            link_tag = f'<a href="{url}" target="_blank">{title}</a>' if url else title
            etsy_items += f"""
            <div class="etsy-item">
                <div class="etsy-title">{link_tag}</div>
                <div class="etsy-source">{source}</div>
                {f'<div class="etsy-summary">{summary}</div>' if summary else ''}
            </div>"""

        if not etsy_items:
            etsy_items = "<div class='empty-state'>No Etsy intelligence found this run.</div>"

        # Build Fine Jewelry Intelligence section
        fine_jewelry_html = ""
        if fine_jewelry_insights:
            fj = fine_jewelry_insights
            
            # Shop rankings table
            shop_rows = ""
            for s in fj.get("shop_rankings", [])[:10]:
                shop_rows += f"""
                <tr>
                    <td class="fj-shop">{s.get('shop_name', '—')}</td>
                    <td class="fj-num">{s.get('total_listings', 0)}</td>
                    <td class="fj-price">${s.get('avg_price', 0):,.0f}</td>
                    <td class="fj-num">{s.get('total_views', 0):,}</td>
                    <td class="fj-num">{s.get('total_favorites', 0):,}</td>
                    <td class="fj-num">{s.get('total_sold', 0):,}</td>
                    <td class="fj-pct">{s.get('conversion_rate', 0):.2f}%</td>
                </tr>"""

            # High-demand listings
            demand_items = ""
            for l in fj.get("high_demand_listings", [])[:8]:
                title = l.get('title', 'Untitled')[:60]
                demand_items += f"""
                <div class="fj-demand-item">
                    <div class="fj-demand-title">{title}</div>
                    <div class="fj-demand-meta">
                        <span class="fj-demand-price">${l.get('price', 0):,.0f}</span>
                        <span class="fj-demand-shop">{l.get('shop_name', '')}</span>
                        <span class="fj-demand-hearts">❤️ {l.get('favorites', 0)}</span>
                        <span class="fj-demand-sold">Sold: {l.get('sold', 0)}</span>
                    </div>
                </div>"""

            # Gold karat breakdown
            gold_rows = ""
            for karat, data in sorted(fj.get("gold_karat_trends", {}).items(),
                                       key=lambda x: x[1]["count"], reverse=True):
                gold_rows += f"""
                <tr>
                    <td class="fj-karat">{karat}</td>
                    <td class="fj-num">{data['count']}</td>
                    <td class="fj-price">${data.get('avg_price', 0):,.0f}</td>
                    <td class="fj-num">{data.get('total_views', 0):,}</td>
                    <td class="fj-num">{data.get('total_favorites', 0):,}</td>
                </tr>"""

            # Top gemstones
            gem_items = ""
            for g in fj.get("top_gemstones", [])[:10]:
                gem_items += f"""
                <div class="fj-gem-item">
                    <span class="fj-gem-name">💎 {g['gemstone']}</span>
                    <span class="fj-gem-count">{g['count']} listings</span>
                    <span class="fj-gem-price">${g.get('avg_price', 0):,.0f} avg</span>
                </div>"""

            # Top tags
            tag_items = ""
            for t in fj.get("top_fine_jewelry_tags", [])[:15]:
                tag_items += f'<span class="fj-tag">#{t["tag"]} ({t["count"]})</span>'

            # Category leaders
            cat_rows = ""
            for cat, data in fj.get("category_leaders", {}).items():
                cat_rows += f"""
                <tr>
                    <td class="fj-cat">{cat.replace('_', ' ').title()}</td>
                    <td class="fj-shop">{data.get('top_shop', '—')}</td>
                    <td class="fj-price">${data.get('avg_shop_price', 0):,.0f}</td>
                    <td class="fj-num">{data.get('total_listings', 0)}</td>
                </tr>"""

            fine_jewelry_html = f"""
            <div class="section fj-section">
                <div class="section-header">
                    <span class="icon">💎</span>
                    <h2>Fine Jewelry Market Intelligence</h2>
                    <span class="badge">{fj.get('total_shops_tracked', 0)} shops · {fj.get('total_listings_collected', 0)} listings</span>
                </div>

                <!-- Summary Cards -->
                <div class="fj-summary-grid">
                    <div class="fj-summary-card">
                        <div class="fj-summary-value">{fj.get('total_shops_tracked', 0)}</div>
                        <div class="fj-summary-label">Shops Tracked</div>
                    </div>
                    <div class="fj-summary-card">
                        <div class="fj-summary-value">{fj.get('total_listings_collected', 0)}</div>
                        <div class="fj-summary-label">Listings Collected</div>
                    </div>
                    <div class="fj-summary-card highlight">
                        <div class="fj-summary-value">${fj.get('avg_listing_price', 0):,.0f}</div>
                        <div class="fj-summary-label">Avg Listing Price</div>
                    </div>
                    <div class="fj-summary-card">
                        <div class="fj-summary-value">${fj.get('total_market_value', 0):,.0f}</div>
                        <div class="fj-summary-label">Total Market Value</div>
                    </div>
                </div>

                <!-- Shop Rankings -->
                <div class="fj-subsection">
                    <h3 class="fj-subsection-title">🏪 Shop Competitive Rankings</h3>
                    <div style="overflow-x: auto;">
                        <table class="fj-table">
                            <thead>
                                <tr>
                                    <th>Shop</th>
                                    <th>Listings</th>
                                    <th>Avg Price</th>
                                    <th>Views</th>
                                    <th>❤️ Favorites</th>
                                    <th>Sold</th>
                                    <th>Conv.</th>
                                </tr>
                            </thead>
                            <tbody>
                                {shop_rows if shop_rows else '<tr><td colspan="7" class="empty">No shop data</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Category Leaders -->
                <div class="fj-subsection">
                    <h3 class="fj-subsection-title">🏆 Category Leaders</h3>
                    <div style="overflow-x: auto;">
                        <table class="fj-table">
                            <thead>
                                <tr>
                                    <th>Category</th>
                                    <th>Top Shop</th>
                                    <th>Avg Price</th>
                                    <th>Total Listings</th>
                                </tr>
                            </thead>
                            <tbody>
                                {cat_rows if cat_rows else '<tr><td colspan="4" class="empty">No category data</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- High-Demand Listings -->
                <div class="fj-subsection">
                    <h3 class="fj-subsection-title">🔥 High-Demand Listings</h3>
                    <div class="fj-demand-grid">
                        {demand_items if demand_items else '<div class="empty-state">No high-demand listings found</div>'}
                    </div>
                </div>

                <!-- Gold Karat Trends -->
                <div class="fj-subsection">
                    <h3 class="fj-subsection-title">🥇 Gold Purity Trends</h3>
                    <div style="overflow-x: auto;">
                        <table class="fj-table">
                            <thead>
                                <tr>
                                    <th>Karat</th>
                                    <th>Listings</th>
                                    <th>Avg Price</th>
                                    <th>Views</th>
                                    <th>❤️ Favorites</th>
                                </tr>
                            </thead>
                            <tbody>
                                {gold_rows if gold_rows else '<tr><td colspan="5" class="empty">No gold data</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Top Gemstones -->
                <div class="fj-subsection">
                    <h3 class="fj-subsection-title">💎 Top Gemstones</h3>
                    <div class="fj-gem-grid">
                        {gem_items if gem_items else '<div class="empty-state">No gemstone data</div>'}
                    </div>
                </div>

                <!-- Top Keywords -->
                <div class="fj-subsection">
                    <h3 class="fj-subsection-title">🏷️ Top SEO Tags</h3>
                    <div class="fj-tag-cloud">
                        {tag_items if tag_items else '<div class="empty-state">No tag data</div>'}
                    </div>
                </div>
            </div>"""

        # Build Google Trends section
        google_trends_html = ""
        if google_trends_report and google_trends_report.total_terms_tracked > 0:
            gt = google_trends_report

            # Rising terms
            rising_items = ""
            for r in gt.rising_google[:8]:
                rising_items += f"""
                <div class="gt-term">
                    <span class="gt-term-name">📈 {r['term']}</span>
                    <span class="gt-term-value">{r.get('current_value', 0)}</span>
                    <span class="gt-term-change up">+{r.get('week_change', 0):+.1f}%</span>
                </div>"""

            # Confirmed trends (Google + Etsy aligned)
            confirmed_items = ""
            for c in gt.confirmed_trends[:5]:
                confirmed_items += f"""
                <div class="gt-confirmed">
                    <span class="gt-confirmed-term">🔥 {c['term']}</span>
                    <span class="gt-confirmed-google">Google: {c.get('google_week_change', 0):+.1f}%</span>
                    <span class="gt-confirmed-etsy">Etsy: {c.get('etsy_direction', '—')}</span>
                </div>"""

            # Category averages
            cat_items = ""
            for cat, val in gt.category_averages.items():
                cat_items += f"""
                <div class="gt-cat-item">
                    <span class="gt-cat-name">{cat.replace('_', ' ').title()}</span>
                    <span class="gt-cat-val">{val}/100</span>
                </div>"""

            google_trends_html = f"""
            <div class="section gt-section">
                <div class="section-header">
                    <span class="icon">📈</span>
                    <h2>Google Trends — Jewelry Search Demand</h2>
                    <span class="badge">{gt.total_terms_tracked} terms · {gt.generated_at[:10]}</span>
                </div>

                <!-- Summary cards -->
                <div class="gt-summary-grid">
                    <div class="gt-summary-card">
                        <div class="gt-summary-value">{len(gt.rising_google)}</div>
                        <div class="gt-summary-label">Rising Terms</div>
                    </div>
                    <div class="gt-summary-card">
                        <div class="gt-summary-value">{len(gt.falling_google)}</div>
                        <div class="gt-summary-label">Falling Terms</div>
                    </div>
                    <div class="gt-summary-card highlight">
                        <div class="gt-summary-value">{len(gt.confirmed_trends)}</div>
                        <div class="gt-summary-label">✅ Confirmed Trends</div>
                    </div>
                    <div class="gt-summary-card">
                        <div class="gt-summary-value">{len(gt.biggest_movers)}</div>
                        <div class="gt-summary-label">Biggest Movers</div>
                    </div>
                </div>

                <!-- Confirmed Trends -->
                {f'''
                <div class="gt-subsection">
                    <h3 class="gt-subsection-title">✅ Confirmed Trends (Google + Etsy Aligned)</h3>
                    <div class="gt-confirmed-grid">{confirmed_items}</div>
                </div>''' if confirmed_items else ''}

                <!-- Rising Terms -->
                <div class="gt-subsection">
                    <h3 class="gt-subsection-title">📈 Rising on Google This Week</h3>
                    <div class="gt-term-grid">
                        {rising_items if rising_items else '<div class="empty-state">No rising terms data</div>'}
                    </div>
                </div>

                <!-- Category Averages -->
                {f'''
                <div class="gt-subsection">
                    <h3 class="gt-subsection-title">📊 Category Search Demand</h3>
                    <div class="gt-cat-grid">{cat_items}</div>
                </div>''' if cat_items else ''}

                <!-- Diverging Signals -->
                {f'''
                <div class="gt-subsection">
                    <h3 class="gt-subsection-title">⚠️ Diverging Signals (Watchlist)</h3>
                    <div class="gt-diverging-grid">
                        {"".join(f'<div class="gt-diverging-item">👀 {d["term"]} — {d.get("note", "")}</div>' for d in gt.diverging_signals[:5])}
                    </div>
                </div>''' if gt.diverging_signals else ''}
            </div>"""

        # Build Pinterest section
        pinterest_html = ""
        if pinterest_report and pinterest_report.total_pins_collected > 0:
            pr = pinterest_report

            # Top pins
            top_pin_items = ""
            for p in pr.top_pins[:8]:
                top_pin_items += f"""
                <div class="pin-item">
                    <div class="pin-title">{p.get('title', 'Untitled')[:60]}</div>
                    <div class="pin-meta">
                        <span>{p.get('save_count', 0)} saves</span>
                        <span>💬 {p.get('comment_count', 0)}</span>
                        <span class="pin-term">#{p.get('search_term', '')}</span>
                    </div>
                </div>"""

            # Trending terms
            term_items = ""
            for t in pr.trending_terms[:8]:
                term_items += f"""
                <div class="pin-term-item">
                    <span class="pin-term-name">🔍 {t['term']}</span>
                    <span class="pin-term-count">{t['count']} pins</span>
                    <span class="pin-term-eng">{t.get('avg_engagement', 0):.0f} avg</span>
                </div>"""

            # Style distribution
            style_items = ""
            for style, count in sorted(pr.style_distribution.items(),
                                        key=lambda x: x[1], reverse=True):
                pct = round(count / pr.total_pins_collected * 100, 1)
                bar_width = max(pct * 3, 5)
                style_items += f"""
                <div class="pin-style-item">
                    <span class="pin-style-name">{style}</span>
                    <div class="pin-style-bar" style="width: {bar_width}px;"></div>
                    <span class="pin-style-pct">{pct}%</span>
                </div>"""

            # Top keywords
            kw_items = ""
            for k in pr.top_keywords[:15]:
                kw_items += f'<span class="pin-kw">#{k["keyword"]} ({k["count"]})</span>'

            pinterest_html = f"""
            <div class="section pin-section">
                <div class="section-header">
                    <span class="icon">📌</span>
                    <h2>Pinterest — Visual Jewelry Trends</h2>
                    <span class="badge">{pr.total_pins_collected} pins · {pr.search_terms_scraped} searches</span>
                </div>

                <!-- Summary -->
                <div class="pin-summary-grid">
                    <div class="pin-summary-card">
                        <div class="pin-summary-value">{pr.total_pins_collected}</div>
                        <div class="pin-summary-label">Pins Collected</div>
                    </div>
                    <div class="pin-summary-card">
                        <div class="pin-summary-value">{pr.search_terms_scraped}</div>
                        <div class="pin-summary-label">Searches</div>
                    </div>
                    <div class="pin-summary-card">
                        <div class="pin-summary-value">{len(pr.trending_terms)}</div>
                        <div class="pin-summary-label">Trending Terms</div>
                    </div>
                    <div class="pin-summary-card highlight">
                        <div class="pin-summary-value">{len(pr.top_keywords)}</div>
                        <div class="pin-summary-label">Trend Keywords</div>
                    </div>
                </div>

                <!-- Top Pins -->
                <div class="pin-subsection">
                    <h3 class="pin-subsection-title">⭐ Top Jewelry Pins</h3>
                    <div class="pin-grid">
                        {top_pin_items if top_pin_items else '<div class="empty-state">No pin data</div>'}
                    </div>
                </div>

                <!-- Trending Terms -->
                <div class="pin-subsection">
                    <h3 class="pin-subsection-title">🔥 Most Searched Jewelry on Pinterest</h3>
                    <div class="pin-term-grid">
                        {term_items if term_items else '<div class="empty-state">No term data</div>'}
                    </div>
                </div>

                <!-- Style Distribution -->
                <div class="pin-subsection">
                    <h3 class="pin-subsection-title">🎨 Style Distribution</h3>
                    <div class="pin-style-grid">
                        {style_items if style_items else '<div class="empty-state">No style data</div>'}
                    </div>
                </div>

                <!-- Keywords -->
                <div class="pin-subsection">
                    <h3 class="pin-subsection-title">🏷️ Top Pin Keywords</h3>
                    <div class="pin-kw-cloud">
                        {kw_items if kw_items else '<div class="empty-state">No keyword data</div>'}
                    </div>
                </div>
            </div>"""

        # Build quick-scan table (Clustered)
        quick_scan_rows = ""
        if articles:
            qs_clusters = self.nlp.cluster_articles(articles[:20])
            for cid, clist in qs_clusters.items():
                representative = clist[0]
                cluster_title = representative.get("title", f"Group {cid}")
                quick_scan_rows += f"""
                <tr class="qs-group-header">
                    <td colspan="3" style="background: #16161d; color: #8899bb; font-weight: 700; font-size: 10px; padding: 8px 12px; border-bottom: 1px solid #2a2a4a; text-transform: uppercase;">
                        📁 Topic: {cluster_title[:90]}{"..." if len(cluster_title) > 90 else ""}
                    </td>
                </tr>"""
                for article in clist:
                    url = article.get("url", "")
                    title = article.get("title", "Untitled")
                    link_tag = f'<a href="{url}" target="_blank">{title[:80]}{"..." if len(title) > 80 else ""}</a>' if url else title[:80]
                    quick_scan_rows += f"""
                    <tr>
                        <td class="qs-source">{article.get("source_name", "")}</td>
                        <td class="qs-date">{article.get("published_date", "")[:10]}</td>
                        <td class="qs-title">{link_tag}</td>
                    </tr>"""

        if not quick_scan_rows:
            quick_scan_rows = "<tr><td colspan='3' class='empty'>No articles captured</td></tr>"

        # Session stats
        succeeded = session_summary.get("sources_succeeded", 0)
        failed = session_summary.get("sources_failed", 0)
        total_articles = session_summary.get("total_articles", len(articles))
        volatility_alerts = session_summary.get("volatility_alerts", [])

        # Build Volatility Alerts HTML
        alerts_html = ""
        if volatility_alerts:
            alerts_html = """
            <div class="section alert-section">
                <div class="section-header">
                    <span class="icon">⚠️</span>
                    <h2 style="color: #ff4d4d;">Market Volatility Alerts</h2>
                </div>
                <div class="alerts-container">"""
            for alert in volatility_alerts:
                alert_class = "surge" if alert["type"] == "Surge" else "crash"
                alerts_html += f"""
                    <div class="alert-item {alert_class}">
                        <div class="alert-title">{alert['commodity'].upper()} {alert['type']}</div>
                        <div class="alert-desc">
                            Price is currently <strong>${alert['price']:,.2f}</strong>. 
                            The Z-Score is <strong>{alert['z_score']:+.2f}</strong>, indicating a significant statistical anomaly.
                        </div>
                    </div>"""
            alerts_html += "</div></div>"

        # Determine theme (light/dark) based on time of day or simply default to dark
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JewelScope Research — Daily Report {report_date}</title>
    <style>
        /* ===== Reset & Base ===== */
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #0f0f12;
            color: #e0e0e0;
            line-height: 1.6;
        }}
        a {{ color: #7c9cff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        /* ===== Header ===== */
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            padding: 32px 40px;
            border-bottom: 1px solid #2a2a4a;
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 700;
            color: #fff;
            margin-bottom: 4px;
        }}
        .header .subtitle {{
            color: #8899bb;
            font-size: 14px;
        }}
        .header .date {{ color: #7c9cff; font-weight: 600; }}

        /* ===== Stats Bar ===== */
        .stats-bar {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 16px;
            padding: 20px 40px;
            background: #16161d;
            border-bottom: 1px solid #222;
        }}
        .stat-box {{
            text-align: center;
            padding: 12px;
            background: #1c1c26;
            border-radius: 8px;
            border: 1px solid #2a2a3a;
        }}
        .stat-box .value {{ font-size: 24px; font-weight: 700; color: #fff; }}
        .stat-box .label {{ font-size: 11px; color: #777; text-transform: uppercase; letter-spacing: 1px; }}
        .stat-box.good .value {{ color: #4caf50; }}
        .stat-box.warn .value {{ color: #ff9800; }}
        .stat-box.bad .value {{ color: #f44336; }}

        /* ===== Content ===== */
        .content {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 32px 24px;
        }}

        /* ===== Section Headers ===== */
        .section {{
            margin-bottom: 40px;
        }}
        .section-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid #2a2a4a;
        }}
        .section-header .icon {{
            font-size: 24px;
        }}
        .section-header h2 {{
            font-size: 20px;
            font-weight: 600;
            color: #fff;
        }}
        .section-header .badge {{
            background: #2a2a4a;
            color: #8899bb;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }}

        /* ===== Headlines ===== */
        .headline-item {{
            display: flex;
            gap: 16px;
            padding: 16px;
            margin-bottom: 8px;
            background: #1a1a24;
            border-radius: 8px;
            border-left: 3px solid #7c9cff;
            transition: background 0.2s;
        }}
        .headline-item:hover {{ background: #222233; }}
        .headline-number {{
            font-size: 18px;
            font-weight: 700;
            color: #7c9cff;
            min-width: 28px;
        }}
        .headline-content {{ flex: 1; }}
        .headline-title {{ font-size: 16px; font-weight: 600; }}
        .headline-meta {{
            display: flex;
            gap: 12px;
            margin-top: 4px;
            font-size: 12px;
        }}
        .headline-source {{ color: #7c9cff; }}
        .headline-date { color: #888; }
        .headline-summary {
            margin-top: 8px;
            color: #aaa;
            font-size: 13px;
        }

        /* New Enrichment Styles */
        .sentiment-badge {
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .sentiment-badge.positive { background: #1b4332; color: #74c69d; }
        .sentiment-badge.negative { background: #5a181d; color: #ff878d; }
        .sentiment-badge.neutral { background: #2b2d42; color: #8d99ae; }

        .headline-keywords {
            margin-top: 10px;
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        .keyword-tag {
            background: #2a2a3a;
            color: #8899bb;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }

        .vision-meta {
            margin-top: 12px;
            display: flex;
            align-items: center;
            gap: 16px;
            padding-top: 8px;
            border-top: 1px solid #2a2a3a;
        }
        .jewelry-badge {
            color: #7c9cff;
            font-size: 12px;
            font-weight: 600;
        }
        .sparkle-badge {
            color: #ffd700;
            font-size: 12px;
            font-weight: 600;
        }
        .color-palette {
            display: flex;
            gap: 4px;
        }
        .color-swatch {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 1px solid #444;
        }

        .headline-image {
            width: 120px;
            height: 80px;
            flex-shrink: 0;
            border-radius: 4px;
            overflow: hidden;
            background: #1c1c26;
            border: 1px solid #2a2a3a;
        }
        .headline-image img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        /* ===== Commodity Prices ===== */

        .commodity-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }}
        .commodity-card {{
            background: #1a1a24;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            border: 1px solid #2a2a3a;
        }}
        .commodity-card .metal {{ font-size: 14px; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }}
        .commodity-card .price {{ font-size: 28px; font-weight: 700; color: #fff; margin: 8px 0; }}
        .commodity-card .change {{ font-size: 13px; }}
        .change.up {{ color: #4caf50; }}
        .change.down {{ color: #f44336; }}
        .commodity-card .gold-border {{ border-top: 3px solid #ffd700; }}
        .commodity-card .silver-border {{ border-top: 3px solid #c0c0c0; }}
        .commodity-card .platinum-border {{ border-top: 3px solid #e5e4e2; }}
        .commodity-card .palladium-border {{ border-top: 3px solid #aaa; }}

        /* ===== Etsy Intelligence ===== */
        .etsy-item {{
            padding: 14px 16px;
            margin-bottom: 8px;
            background: #1a1a24;
            border-radius: 8px;
            border-left: 3px solid #f56400;
        }}
        .etsy-title {{ font-weight: 600; }}
        .etsy-source {{ font-size: 12px; color: #f56400; margin-top: 2px; }}
        .etsy-summary {{ color: #aaa; font-size: 13px; margin-top: 6px; }}

        /* ===== Quick Scan Table ===== */
        .quick-scan {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .quick-scan th {{
            text-align: left;
            padding: 10px 12px;
            background: #1a1a24;
            color: #8899bb;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 1px;
            border-bottom: 2px solid #2a2a4a;
        }}
        .quick-scan td {{
            padding: 10px 12px;
            border-bottom: 1px solid #222;
        }}
        .quick-scan tr:hover {{ background: #1c1c2a; }}
        .qs-source { color: #7c9cff; font-weight: 500; }
        .qs-date { color: #888; white-space: nowrap; }

        .cluster-header {
            background: #1c1c2b;
            padding: 12px 16px;
            margin: 24px 0 12px 0;
            border-radius: 6px;
            border-left: 4px solid #7c9cff;
            color: #7c9cff;
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .cluster-icon { font-size: 18px; }

        .empty-state {
            padding: 32px;
            text-align: center;
            color: #666;
            font-style: italic;
        }

        .empty {{ color: #666; text-align: center; padding: 20px; }}

        /* ===== Volatility Alerts ===== */
        .alert-section { margin-top: 20px; }
        .alerts-container { display: flex; flex-direction: column; gap: 12px; }
        .alert-item {
            padding: 16px;
            border-radius: 8px;
            border-left: 5px solid;
            background: #1c1c26;
        }
        .alert-item.surge { border-left-color: #4caf50; }
        .alert-item.crash { border-left-color: #f44336; }
        .alert-title { font-weight: 700; font-size: 16px; margin-bottom: 4px; }
        .alert-desc { font-size: 14px; color: #ccc; }

        /* ===== Footer ===== */
        .footer {{
            text-align: center;
            padding: 24px;
            color: #555;
            font-size: 12px;
            border-top: 1px solid #222;
            margin-top: 40px;
        }}
        .footer .disclaimer {{
            margin-top: 8px;
            color: #444;
            font-style: italic;
        }}

        /* ===== Print Styles ===== */
        @media print {{
            body {{ background: #fff; color: #333; }}
            .header {{ background: #f5f5f5 !important; color: #333; }}
            .header h1 {{ color: #333; }}
            .stat-box {{ background: #f5f5f5; border-color: #ddd; }}
            .stat-box .value {{ color: #333; }}
            .headline-item, .etsy-item, .commodity-card {{ background: #fafafa; border-color: #ddd; }}
            .quick-scan th {{ background: #f5f5f5; color: #333; }}
            .quick-scan td {{ border-color: #ddd; }}
            a {{ color: #1a56db; }}
            .section-header h2 {{ color: #333; }}
            .headline-number {{ color: #1a56db; }}
            .headline-source {{ color: #1a56db; }}
            .qs-source {{ color: #1a56db; }}
        }}

        /* ===== Fine Jewelry Intelligence Styles ===== */
        .fj-section {{ margin-top: 40px; }}
        .fj-summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 28px; }}
        .fj-summary-card {{ background: linear-gradient(135deg, #1a1a2e, #1c1c2e); border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #2a2a4a; }}
        .fj-summary-card.highlight {{ border-color: #ffd700; background: linear-gradient(135deg, #1a1a2e, #2a2a1e); }}
        .fj-summary-value {{ font-size: 26px; font-weight: 700; color: #fff; }}
        .fj-summary-card.highlight .fj-summary-value {{ color: #ffd700; }}
        .fj-summary-label {{ font-size: 11px; color: #8899bb; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }}

        .fj-subsection {{ margin-bottom: 28px; }}
        .fj-subsection-title {{ font-size: 16px; font-weight: 600; color: #ccd; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #2a2a3a; }}

        .fj-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        .fj-table th {{ text-align: left; padding: 10px 12px; background: #1a1a24; color: #8899bb; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 1px; border-bottom: 2px solid #2a2a4a; }}
        .fj-table td {{ padding: 10px 12px; border-bottom: 1px solid #222; }}
        .fj-table tr:hover {{ background: #1c1c2a; }}
        .fj-shop {{ color: #7c9cff; font-weight: 500; }}
        .fj-num {{ color: #ddd; text-align: right; font-variant-numeric: tabular-nums; }}
        .fj-price {{ color: #4caf50; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }}
        .fj-pct {{ color: #ff9800; text-align: right; }}
        .fj-karat {{ color: #ffd700; font-weight: 600; }}
        .fj-cat {{ color: #ccd; font-weight: 500; }}

        .fj-demand-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
        .fj-demand-item {{ background: #1a1a24; border-radius: 8px; padding: 14px 16px; border-left: 3px solid #ff9800; }}
        .fj-demand-title {{ font-weight: 600; font-size: 14px; color: #fff; margin-bottom: 6px; }}
        .fj-demand-meta {{ display: flex; gap: 12px; font-size: 12px; flex-wrap: wrap; }}
        .fj-demand-price {{ color: #4caf50; font-weight: 700; }}
        .fj-demand-shop {{ color: #7c9cff; }}
        .fj-demand-hearts {{ color: #ff6b9d; }}
        .fj-demand-sold {{ color: #888; }}

        .fj-gem-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .fj-gem-item {{ display: flex; gap: 12px; align-items: center; background: #1a1a24; border-radius: 8px; padding: 10px 14px; border: 1px solid #2a2a3a; min-width: 220px; }}
        .fj-gem-name {{ font-weight: 600; color: #ccd; min-width: 100px; }}
        .fj-gem-count {{ color: #8899bb; font-size: 12px; }}
        .fj-gem-price {{ color: #4caf50; font-weight: 600; margin-left: auto; font-size: 12px; }}

        .fj-tag-cloud {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .fj-tag {{ background: #1a1a2e; color: #7c9cff; padding: 4px 12px; border-radius: 16px; font-size: 12px; border: 1px solid #2a2a4a; }}

        /* ===== Google Trends Styles ===== */
        .gt-section {{ margin-top: 40px; }}
        .gt-summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 28px; }}
        .gt-summary-card {{ background: linear-gradient(135deg, #1a1a2e, #1c1c2e); border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #2a2a4a; }}
        .gt-summary-card.highlight {{ border-color: #4caf50; background: linear-gradient(135deg, #1a2a1e, #1c2e1e); }}
        .gt-summary-value {{ font-size: 26px; font-weight: 700; color: #fff; }}
        .gt-summary-card.highlight .gt-summary-value {{ color: #4caf50; }}
        .gt-summary-label {{ font-size: 11px; color: #8899bb; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }}

        .gt-subsection {{ margin-bottom: 28px; }}
        .gt-subsection-title {{ font-size: 16px; font-weight: 600; color: #ccd; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #2a2a3a; }}

        .gt-term-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px; }}
        .gt-term {{ display: flex; gap: 12px; align-items: center; background: #1a1a24; border-radius: 8px; padding: 10px 14px; border: 1px solid #2a2a3a; }}
        .gt-term-name {{ font-weight: 600; color: #ccd; flex: 1; font-size: 13px; }}
        .gt-term-value {{ color: #8899bb; font-size: 14px; font-weight: 700; }}
        .gt-term-change {{ font-weight: 700; font-size: 12px; }}
        .gt-term-change.up {{ color: #4caf50; }}
        .gt-term-change.down {{ color: #f44336; }}

        .gt-confirmed-grid {{ display: flex; flex-direction: column; gap: 8px; }}
        .gt-confirmed {{ display: flex; gap: 16px; align-items: center; background: #1a2a1e; border-radius: 8px; padding: 12px 16px; border-left: 3px solid #4caf50; }}
        .gt-confirmed-term {{ font-weight: 600; color: #74c69d; flex: 1; }}
        .gt-confirmed-google {{ color: #8899bb; font-size: 12px; }}
        .gt-confirmed-etsy {{ color: #7c9cff; font-size: 12px; }}

        .gt-cat-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .gt-cat-item {{ display: flex; gap: 12px; align-items: center; background: #1a1a24; border-radius: 8px; padding: 10px 14px; border: 1px solid #2a2a3a; }}
        .gt-cat-name {{ font-weight: 600; color: #ccd; min-width: 100px; font-size: 13px; }}
        .gt-cat-val {{ color: #7c9cff; font-weight: 700; font-size: 14px; }}

        .gt-diverging-grid {{ display: flex; flex-direction: column; gap: 8px; }}
        .gt-diverging-item {{ background: #2a1e1e; border-radius: 8px; padding: 10px 14px; border-left: 3px solid #ff9800; color: #ccc; font-size: 13px; }}

        /* ===== Pinterest Styles ===== */
        .pin-section {{ margin-top: 40px; }}
        .pin-summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 28px; }}
        .pin-summary-card {{ background: linear-gradient(135deg, #1a1a2e, #1c1c2e); border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #2a2a4a; }}
        .pin-summary-card.highlight {{ border-color: #e60023; background: linear-gradient(135deg, #2a1a1e, #2e1c1e); }}
        .pin-summary-value {{ font-size: 26px; font-weight: 700; color: #fff; }}
        .pin-summary-card.highlight .pin-summary-value {{ color: #e60023; }}
        .pin-summary-label {{ font-size: 11px; color: #8899bb; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }}

        .pin-subsection {{ margin-bottom: 28px; }}
        .pin-subsection-title {{ font-size: 16px; font-weight: 600; color: #ccd; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #2a2a3a; }}

        .pin-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px; }}
        .pin-item {{ background: #1a1a24; border-radius: 8px; padding: 12px 14px; border: 1px solid #2a2a3a; border-left: 3px solid #e60023; }}
        .pin-title {{ font-weight: 600; font-size: 14px; color: #fff; margin-bottom: 6px; }}
        .pin-meta {{ display: flex; gap: 10px; font-size: 12px; color: #8899bb; }}
        .pin-term {{ color: #e60023; }}

        .pin-term-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px; }}
        .pin-term-item {{ display: flex; gap: 10px; align-items: center; background: #1a1a24; border-radius: 8px; padding: 10px 14px; border: 1px solid #2a2a3a; }}
        .pin-term-name {{ font-weight: 600; color: #ccd; flex: 1; font-size: 13px; }}
        .pin-term-count {{ color: #8899bb; font-size: 12px; }}
        .pin-term-eng {{ color: #e60023; font-weight: 600; font-size: 12px; }}

        .pin-style-grid {{ display: flex; flex-direction: column; gap: 8px; }}
        .pin-style-item {{ display: flex; gap: 12px; align-items: center; background: #1a1a24; border-radius: 6px; padding: 8px 12px; }}
        .pin-style-name {{ font-weight: 600; color: #ccd; min-width: 90px; font-size: 13px; }}
        .pin-style-bar {{ height: 10px; background: linear-gradient(90deg, #e60023, #ff6b81); border-radius: 5px; }}
        .pin-style-pct {{ color: #8899bb; font-size: 12px; min-width: 40px; text-align: right; }}

        .pin-kw-cloud {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .pin-kw {{ background: #1a1a2e; color: #e60023; padding: 4px 12px; border-radius: 16px; font-size: 12px; border: 1px solid #2a2a4a; }}
    </style>
</head>
<body>

    <!-- Header -->
    <div class="header">
        <h1>💎 JewelScope Research</h1>
        <div class="subtitle">
            Daily Intelligence Report &middot; <span class="date">{report_date}</span>
        </div>
    </div>

    <!-- Stats Bar -->
    <div class="stats-bar">
        <div class="stat-box">
            <div class="value">{total_articles}</div>
            <div class="label">Articles Found</div>
        </div>
        <div class="stat-box">
            <div class="value">{succeeded}</div>
            <div class="label">Sources OK</div>
        </div>
        <div class="stat-box {'bad' if failed > 0 else 'good'}">
            <div class="value">{failed}</div>
            <div class="label">Sources Failed</div>
        </div>
        <div class="stat-box">
            <div class="value">{len(headlines)}</div>
            <div class="label">Top Headlines</div>
        </div>
        <div class="stat-box">
            <div class="value">{len(etsy_intel)}</div>
            <div class="label">Etsy Posts</div>
        </div>
    </div>

    <!-- Content -->
    <div class="content">
        {alerts_html}

        <!-- Commodity Prices -->
        <div class="section">
            <div class="section-header">
                <span class="icon">📊</span>
                <h2>Precious Metal Prices</h2>
                <span class="badge">spot • troy oz</span>
            </div>
            <div class="commodity-grid">
                {commodity_rows}
            </div>
        </div>

        <!-- Top Headlines -->
        <div class="section">
            <div class="section-header">
                <span class="icon">📰</span>
                <h2>Top 10 Industry Headlines</h2>
                <span class="badge">curated</span>
            </div>
            {headline_items}
        </div>

        <!-- Etsy Intelligence -->
        <div class="section">
            <div class="section-header">
                <span class="icon">🛒</span>
                <h2>Etsy Intelligence</h2>
                <span class="badge">seller insights</span>
            </div>
            {etsy_items}
        </div>

        <!-- Fine Jewelry Market Intelligence -->
        {fine_jewelry_html}

        <!-- Google Trends — Jewelry Search Demand -->
        {google_trends_html}

        <!-- Pinterest — Visual Trend Signals -->
        {pinterest_html}

        <!-- Quick Scan Table -->
        <div class="section">
            <div class="section-header">
                <span class="icon">⚡</span>
                <h2>Quick Scan</h2>
                <span class="badge">all sources</span>
            </div>
            <div style="overflow-x: auto;">
                <table class="quick-scan">
                    <thead>
                        <tr>
                            <th>Source</th>
                            <th>Date</th>
                            <th>Headline / Summary</th>
                        </tr>
                    </thead>
                    <tbody>
                        {quick_scan_rows}
                    </tbody>
                </table>
            </div>
        </div>

    </div>

    <!-- Footer -->
    <div class="footer">
        <p>Generated by JewelScope Research v1.0 &bull; {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <p class="disclaimer">
            Disclaimer: This report aggregates publicly available information for research purposes.
            Users are responsible for complying with each source website's Terms of Service and robots.txt.
            Data may not be reproduced without permission from original sources.
        </p>
    </div>

</body>
</html>"""

        return html

    def generate_pdf(self, html_path: str) -> Optional[str]:
        """Convert HTML report to PDF using weasyprint."""
        try:
            from weasyprint import HTML
            pdf_path = html_path.rsplit(".", 1)[0] + ".pdf"
            HTML(filename=html_path).write_pdf(pdf_path)
            logger.info(f"PDF generated: {pdf_path}")
            return pdf_path
        except ImportError:
            logger.warning("weasyprint not installed — PDF generation unavailable")
            return None
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            return None
