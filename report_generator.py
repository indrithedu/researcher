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
                      report_date: date = None) -> str:
        """
        Generate a complete HTML report.
        Returns: path to the generated HTML file.
        """
        report_date = report_date or date.today()
        html_content = self._build_html(
            articles=articles,
            headlines=headlines,
            etsy_intel=etsy_intel,
            commodity_prices=commodity_prices,
            session_summary=session_summary or {},
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
                    session_summary, report_date) -> str:
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
        .headline-date {{ color: #888; }}
        .headline-summary {{
            margin-top: 8px;
            color: #aaa;
            font-size: 13px;
        }}

        /* New Enrichment Styles */
        .sentiment-badge {{
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .sentiment-badge.positive {{ background: #1b4332; color: #74c69d; }}
        .sentiment-badge.negative {{ background: #5a181d; color: #ff878d; }}
        .sentiment-badge.neutral {{ background: #2b2d42; color: #8d99ae; }}

        .headline-keywords {{
            margin-top: 10px;
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .keyword-tag {{
            background: #2a2a3a;
            color: #8899bb;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}

        .vision-meta {{
            margin-top: 12px;
            display: flex;
            align-items: center;
            gap: 16px;
            padding-top: 8px;
            border-top: 1px solid #2a2a3a;
        }}
        .jewelry-badge {{
            color: #7c9cff;
            font-size: 12px;
            font-weight: 600;
        }}
        .sparkle-badge {{
            color: #ffd700;
            font-size: 12px;
            font-weight: 600;
        }}
        .color-palette {{
            display: flex;
            gap: 4px;
        }}
        .color-swatch {{
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 1px solid #444;
        }}

        .headline-image {{
            width: 120px;
            height: 80px;
            flex-shrink: 0;
            border-radius: 4px;
            overflow: hidden;
            background: #1c1c26;
            border: 1px solid #2a2a3a;
        }}
        .headline-image img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

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
        .qs-source {{ color: #7c9cff; font-weight: 500; }}
        .qs-date {{ color: #888; white-space: nowrap; }}

        .cluster-header {{
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
        }}
        .cluster-icon {{ font-size: 18px; }}

        .empty-state {{
            padding: 32px;
            text-align: center;
            color: #666;
            font-style: italic;
        }}

        .empty {{ color: #666; text-align: center; padding: 20px; }}

        /* ===== Volatility Alerts ===== */
        .alert-section {{ margin-top: 20px; }}
        .alerts-container {{ display: flex; flex-direction: column; gap: 12px; }}
        .alert-item {{
            padding: 16px;
            border-radius: 8px;
            border-left: 5px solid;
            background: #1c1c26;
        }}
        .alert-item.surge {{ border-left-color: #4caf50; }}
        .alert-item.crash {{ border-left-color: #f44336; }}
        .alert-title {{ font-weight: 700; font-size: 16px; margin-bottom: 4px; }}
        .alert-desc {{ font-size: 14px; color: #ccc; }}

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
