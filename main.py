# =============================================================================
# JewelScope Research — Main Application (Streamlit UI)
# =============================================================================
#
# Streamlit web UI for the JewelScope Research app.
# Features:
#   - Dashboard with latest stats and commodity prices
#   - Manual scan trigger with real-time progress
#   - Past reports browser with HTML preview
#   - Source configuration editor
#   - Settings (proxies, email, CAPTCHA)
#   - Daily report viewing
#
# Run: streamlit run main.py
# =============================================================================

import os
import sys
import json
import logging
import threading
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

import yaml
import streamlit as st

from logic import (
    load_config, 
    save_config, 
    get_database, 
    get_anti_detect_client, 
    run_full_scrape,
    APP_DIR,
    CONFIG_PATH,
    DB_PATH,
    REPORT_DIR
)

# Ensure directories exist (already handled in logic.py, but safe to keep)
os.makedirs(os.path.join(APP_DIR, "databases"), exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# =============================================================================
# Streamlit UI
# =============================================================================

def main_ui():
    st.set_page_config(
        page_title="JewelScope Research",
        page_icon="💎",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS
    with open("static/styles.css", "r") as f:
        css = f.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # Initialize session state
    if "scan_results" not in st.session_state:
        st.session_state.scan_results = None
    if "scan_in_progress" not in st.session_state:
        st.session_state.scan_in_progress = False
    if "config_modified" not in st.session_state:
        st.session_state.config_modified = False

    # =============================================================================
    # Sidebar
    # =============================================================================

    with st.sidebar:
        st.markdown("### 💎 JewelScope")
        st.markdown("Personal Content Researcher")
        st.markdown("---")

        # Navigation
        page = st.radio(
            "Navigate",
            ["📊 Dashboard", "📈 Trend Intelligence", "🔍 Run Scan", "📄 Past Reports", "⚙️ Settings"],
            label_visibility="collapsed",
        )

        st.markdown("---")

        # Quick stats
        try:
            db = get_database()
            stats = db.get_stats()
            st.metric("Total Articles", stats.get("total_articles", 0))
            st.metric("Scans Run", stats.get("total_sessions", 0))
            st.metric("Reports Generated", stats.get("total_reports", 0))

            latest = stats.get("latest_session")
            if latest:
                st.caption(f"Last scan: {latest.started_at.strftime('%b %d, %H:%M')}")
        except Exception as e:
            st.caption("Database not initialized yet")

        st.markdown("---")
        st.caption("JewelScope Research v1.0")
        st.caption("⚠️ Respect each site's ToS & robots.txt")

    # =============================================================================
    # Pages
    # =============================================================================

    if page == "📊 Dashboard":
        # ========== DASHBOARD ==========
        st.title("📊 Research Dashboard")

        # Get latest data
        try:
            db = get_database()
            stats = db.get_stats()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📰 Articles Collected", stats.get("total_articles", 0))
            with col2:
                st.metric("🔍 Scraping Runs", stats.get("total_sessions", 0))
            with col3:
                st.metric("📄 Reports Generated", stats.get("total_reports", 0))
            with col4:
                sources = stats.get("sources_with_data", 0)
                st.metric("🌐 Active Sources", sources)

            # Latest commodity prices
            st.subheader("💲 Latest Commodity Prices")
            prices = db.get_latest_commodity_prices()
            if prices:
                cols = st.columns(len(prices))
                for i, (commodity, price) in enumerate(prices.items()):
                    with cols[i]:
                        icon = {"gold": "🥇", "silver": "🥈", "platinum": "🔘", "palladium": "⚪"}.get(
                            commodity.lower(), "💎"
                        )
                        st.metric(f"{icon} {commodity.title()}", f"${price:,.2f}", "per oz")
            else:
                st.info("No commodity prices yet. Run a scan to fetch them.")

            # Latest reports
            st.subheader("📄 Recent Reports")
            reports = db.get_recent_reports(limit=5)
            if reports:
                for r in reports:
                    with st.expander(f"📆 {r.report_date} — Session #{r.session_id}"):
                        meta = r.get_metadata()
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Articles", meta.get("total_articles", "?"))
                        col2.metric("Sources OK", meta.get("sources_succeeded", "?"))
                        col3.metric("Failed", meta.get("sources_failed", "?"))

                        if r.html_path and os.path.exists(r.html_path):
                            with open(r.html_path, "r") as f:
                                html_content = f.read()
                            st.download_button(
                                "📥 Download HTML Report",
                                data=html_content,
                                file_name=os.path.basename(r.html_path),
                                mime="text/html",
                            )
                        if r.pdf_path and os.path.exists(r.pdf_path):
                            with open(r.pdf_path, "rb") as f:
                                st.download_button(
                                    "📥 Download PDF Report",
                                    data=f,
                                    file_name=os.path.basename(r.pdf_path),
                                    mime="application/pdf",
                                )
            else:
                st.info("No reports yet. Run your first scan from the 'Run Scan' tab!")

            # Latest articles
            st.subheader("📰 Latest Articles")
            latest_articles = db.get_latest_articles(limit=10)
            if latest_articles:
                for a in latest_articles:
                    st.markdown(
                        f"**[{a.source_name}]** [{a.title}]({a.url})  "
                        f"*{a.published_date or ''}*"
                    )
                    if a.summary:
                        st.caption(a.summary[:200])
                    st.divider()
            else:
                st.info("No articles yet. Start a scan!")

        except Exception as e:
            st.error(f"Dashboard error: {e}")
            st.info("Run your first scan to populate the dashboard!")

    elif page == "📈 Trend Intelligence":
        # ========== TREND INTELLIGENCE ==========
        st.title("📈 Trend Intelligence")
        st.markdown("Visualize which jewelry keywords are rising in popularity based on collected articles.")

        try:
            db = get_database()
            
            col1, col2 = st.columns([1, 3])
            with col1:
                days = st.slider("Momentum Period (days)", min_value=1, max_value=30, value=7)
            
            momentum_data = db.get_keyword_momentum(days=days)
            
            if momentum_data:
                # Top Movers Metrics
                st.subheader("🚀 Top Rising Keywords")
                top_movers = [m for m in momentum_data if m["momentum"] > 0][:3]
                if top_movers:
                    cols = st.columns(len(top_movers))
                    for i, mover in enumerate(top_movers):
                        with cols[i]:
                            st.metric(
                                label=mover["keyword"].title(),
                                value=mover["count"],
                                delta=f"{mover['momentum']*100:.1f}%",
                            )
                else:
                    st.info("No rising keywords found for this period.")
                
                # Momentum Table
                st.subheader("📊 Keyword Momentum Analysis")
                import pandas as pd
                df = pd.DataFrame(momentum_data)
                # Rename columns for display
                df_display = df.rename(columns={
                    "keyword": "Keyword",
                    "count": "Current Count",
                    "previous_count": "Previous Count",
                    "momentum": "Momentum"
                })
                # Format momentum as percentage
                df_display["Momentum"] = df_display["Momentum"].apply(lambda x: f"{x*100:.1f}%")
                
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                
                # Bar chart of top 20 by count
                st.subheader("🔥 Most Frequent Keywords (Current Period)")
                top_20_count = sorted(momentum_data, key=lambda x: x["count"], reverse=True)[:20]
                chart_df = pd.DataFrame(top_20_count)
                st.bar_chart(chart_df, x="keyword", y="count")
            else:
                st.info("Not enough data to calculate momentum. Try increasing the period or running more scans.")
                
        except Exception as e:
            st.error(f"Trend Analysis error: {e}")
            logger.error("Trend Analysis failed", exc_info=True)

    elif page == "🔍 Run Scan":
        # ========== RUN SCAN ==========
        st.title("🔍 Manual Research Scan")
        st.markdown("Scrape all configured news sources and generate a daily report.")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            show_source_count = st.empty()
        with col2:
            run_btn = st.button("🚀 Start Scan", type="primary", use_container_width=True)
        with col3:
            save_btn = st.download_button(
                "💾 Save Last Report",
                data="",
                disabled=True,
                use_container_width=True,
            )

        # Progress indicators
        progress_bar = st.progress(0, text="Ready")
        status_text = st.empty()

        if run_btn and not st.session_state.scan_in_progress:
            st.session_state.scan_in_progress = True
            status_text.info("Initializing scraper...")

            try:
                config = load_config()
                enabled_sources = sum(
                    1 for s in config.get("sources", {}).values() if s.get("enabled", True)
                )
                show_source_count.metric("Active Sources", enabled_sources)

                # Simulate progress (we can't get real-time updates from a thread easily)
                progress_bar.progress(10, text="Connecting to sources...")

                # Run the scrape in the main thread (Streamlit handles concurrency)
                result = run_full_scrape(config)

                st.session_state.scan_results = result

                progress_bar.progress(100, text="Complete!")

                if result["errors"]:
                    status_text.warning(
                        f"Scan complete with {len(result['errors'])} source errors. "
                        f"{result['sources_succeeded']} sources OK, "
                        f"{result['sources_failed']} failed."
                    )
                    with st.expander("⚠️ Error Details"):
                        for err in result["errors"][:10]:
                            st.code(err)
                else:
                    status_text.success(
                        f"✅ Scan complete! Found {result['total_articles']} articles "
                        f"from {result['sources_succeeded']} sources."
                    )

            except Exception as e:
                status_text.error(f"Scan failed: {e}")
                logger.error("Scan failed", exc_info=True)
            finally:
                st.session_state.scan_in_progress = False

        elif st.session_state.scan_in_progress:
            st.warning("A scan is already in progress. Please wait...")

        # Display results if we have them
        if st.session_state.scan_results:
            result = st.session_state.scan_results

            st.markdown("---")
            st.subheader("📊 Scan Results")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Articles Found", result["total_articles"])
            col2.metric("Sources OK", result["sources_succeeded"])
            col3.metric("Failed", result["sources_failed"])
            col4.metric("Headlines", len(result["headlines"]))

            # Report downloads
            if result.get("html_path") and os.path.exists(result["html_path"]):
                with open(result["html_path"], "r") as f:
                    html_content = f.read()
                st.download_button(
                    "📥 Download HTML Report",
                    data=html_content,
                    file_name=os.path.basename(result["html_path"]),
                    mime="text/html",
                    use_container_width=True,
                )

            if result.get("pdf_path") and os.path.exists(result["pdf_path"]):
                with open(result["pdf_path"], "rb") as f:
                    st.download_button(
                        "📥 Download PDF Report",
                        data=f,
                        file_name=os.path.basename(result["pdf_path"]),
                        mime="application/pdf",
                        use_container_width=True,
                    )

            # Preview headlines
            if result["headlines"]:
                st.subheader("📰 Top Headlines")
                for i, h in enumerate(result["headlines"][:5], 1):
                    st.markdown(
                        f"{i}. **[{h['source_name']}]** "
                        f"[{h['title']}]({h['url']})"
                    )
                    if h.get("summary"):
                        st.caption(h["summary"][:200])

            # Etsy intelligence
            if result["etsy_intel"]:
                st.subheader("🛒 Etsy Intelligence")
                for e in result["etsy_intel"][:5]:
                    st.markdown(f"- [{e['title']}]({e['url']}) — *{e['source_name']}*")

            # Commodity prices
            if result["commodity_prices"]:
                st.subheader("💲 Commodity Prices")
                for cp in result["commodity_prices"]:
                    st.markdown(f"- **{cp['title']}**")

        # Schedule status
        st.markdown("---")
        st.subheader("⏰ Scheduled Runs")
        config = load_config()
        sched_config = config.get("scheduling", {})
        if sched_config.get("enabled", True):
            st.info(f"Daily scan scheduled: cron `{sched_config.get('cron', '0 7 * * *')}`")
        else:
            st.info("Scheduled scanning is disabled. Enable it in Settings.")

    elif page == "📄 Past Reports":
        # ========== PAST REPORTS ==========
        st.title("📄 Past Reports")

        try:
            db = get_database()
            reports = db.get_recent_reports(limit=50)

            if not reports:
                st.info("No reports yet. Run your first scan!")
            else:
                # Date filter
                dates = sorted(set(r.report_date for r in reports), reverse=True)
                selected_date = st.selectbox("Filter by date", ["All"] + dates)

                filtered = [
                    r for r in reports
                    if selected_date == "All" or r.report_date == selected_date
                ]

                for r in filtered:
                    meta = r.get_metadata()
                    with st.expander(f"📆 {r.report_date} — Session #{r.session_id}"):
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Articles", meta.get("total_articles", "?"))
                        col2.metric("Sources OK", meta.get("sources_succeeded", "?"))
                        col3.metric("Failed", meta.get("sources_failed", "?"))

                        # Preview the HTML report inline
                        if r.html_path and os.path.exists(r.html_path):
                            with open(r.html_path, "r") as f:
                                html_content = f.read()

                            tab1, tab2 = st.tabs(["Preview", "Download"])

                            with tab1:
                                st.components.v1.html(html_content, height=600, scrolling=True)

                            with tab2:
                                st.download_button(
                                    "📥 Download HTML",
                                    data=html_content,
                                    file_name=os.path.basename(r.html_path),
                                    mime="text/html",
                                )

                                if r.pdf_path and os.path.exists(r.pdf_path):
                                    with open(r.pdf_path, "rb") as f:
                                        st.download_button(
                                            "📥 Download PDF",
                                            data=f,
                                            file_name=os.path.basename(r.pdf_path),
                                            mime="application/pdf",
                                        )

                        # Show articles from this session
                        articles = db.get_articles_by_session(r.session_id)
                        if articles:
                            with st.expander(f"📰 All {len(articles)} articles from this session"):
                                for a in articles[:30]:
                                    st.markdown(
                                        f"- [{a.title}]({a.url}) *({a.source_name}, {a.published_date or ''})*"
                                    )
                                if len(articles) > 30:
                                    st.caption(f"... and {len(articles) - 30} more")

        except Exception as e:
            st.error(f"Could not load reports: {e}")

    elif page == "⚙️ Settings":
        # ========== SETTINGS ==========
        st.title("⚙️ Settings")

        config = load_config()

        tab1, tab2, tab3, tab4 = st.tabs([
            "📰 Sources", "🛡️ Anti-Detection", "⏰ Scheduling", "📧 Email"
        ])

        # --- Sources Tab ---
        with tab1:
            st.subheader("News Sources")
            st.markdown("Enable/disable individual sources or add new ones.")

            sources = config.get("sources", {})

            source_names = list(sources.keys())
            cols = st.columns(2)
            updated_sources = {}

            for i, name in enumerate(source_names):
                source = sources[name]
                with cols[i % 2]:
                    with st.container(border=True):
                        enabled = st.toggle(
                            "Enabled",
                            value=source.get("enabled", True),
                            key=f"src_enabled_{name}",
                        )
                        display_name = st.text_input(
                            "Display Name",
                            value=source.get("name", name),
                            key=f"src_name_{name}",
                        )
                        url = st.text_input(
                            "URL",
                            value=source.get("url", ""),
                            key=f"src_url_{name}",
                        )
                        src_type = st.selectbox(
                            "Type",
                            options=["article_list", "rss", "commodity", "reddit", "js"],
                            index=["article_list", "rss", "commodity", "reddit", "js"].index(
                                source.get("type", "article_list")
                            ),
                            key=f"src_type_{name}",
                        )

                        updated_sources[name] = {
                            "name": display_name,
                            "url": url,
                            "type": src_type,
                            "enabled": enabled,
                            "selectors": source.get("selectors", {}),
                        }

            # Add new source
            with st.expander("➕ Add New Source"):
                new_name = st.text_input("Source Key (e.g., 'my_jewelry_blog')", key="new_src_key")
                new_display = st.text_input("Display Name", key="new_src_display")
                new_url = st.text_input("URL", key="new_src_url")
                new_type = st.selectbox(
                    "Type",
                    ["article_list", "rss", "commodity", "reddit", "js"],
                    key="new_src_type",
                )

                if st.button("Add Source") and new_name and new_url:
                    updated_sources[new_name] = {
                        "name": new_display or new_name,
                        "url": new_url,
                        "type": new_type,
                        "enabled": True,
                        "selectors": {},
                    }
                    st.success(f"Added {new_name}! Save changes below.")
                    st.rerun()

            # Remove source
            with st.expander("🗑️ Remove Source"):
                to_remove = st.selectbox("Select source to remove", [""] + source_names)
                if to_remove and st.button("Remove", type="primary"):
                    if to_remove in updated_sources:
                        del updated_sources[to_remove]
                        st.success(f"Removed {to_remove}!")
                        st.rerun()

            if st.button("💾 Save Source Changes", type="primary"):
                config["sources"] = updated_sources
                save_config(config)
                st.success("Sources saved! Changes take effect on next scan.")

        # --- Anti-Detection Tab ---
        with tab2:
            st.subheader("🛡️ Anti-Detection Engine")
            st.markdown(
                "Configure how the scraper bypasses bot detection. "
                "These settings control request timing, proxies, and CAPTCHA solving."
            )

            ad = config.get("anti_detection", {})

            ad["enabled"] = st.toggle("Enable Anti-Detection", value=ad.get("enabled", True))

            col1, col2 = st.columns(2)
            with col1:
                ad["request_delay_min"] = st.number_input(
                    "Min Delay (seconds)", min_value=1, max_value=60,
                    value=ad.get("request_delay_min", 5),
                )
                ad["max_retries"] = st.number_input(
                    "Max Retries", min_value=0, max_value=10,
                    value=ad.get("max_retries", 3),
                )
            with col2:
                ad["request_delay_max"] = st.number_input(
                    "Max Delay (seconds)", min_value=1, max_value=120,
                    value=ad.get("request_delay_max", 25),
                )
                ad["proxy_strategy"] = st.selectbox(
                    "Proxy Strategy",
                    ["random", "round_robin"],
                    index=0 if ad.get("proxy_strategy", "random") == "random" else 1,
                )

            # Proxy configuration
            st.subheader("🌐 Proxy Pool")
            st.markdown(
                "Add proxies one per line. Format: `http://user:pass@host:port` "
                "or `socks5://user:pass@host:port`"
            )

            current_proxies = ad.get("proxies", [""])
            proxy_text = "\n".join(p for p in current_proxies if p and p.strip())
            proxy_text = st.text_area(
                "Proxies (one per line)",
                value=proxy_text,
                height=100,
                placeholder="http://user:pass@proxy1.example.com:8080\nsocks5://user:pass@proxy2.example.com:1080",
            )
            ad["proxies"] = [""]  # Keep empty string as fallback
            for line in proxy_text.strip().split("\n"):
                line = line.strip()
                if line:
                    ad["proxies"].append(line)

            # CAPTCHA configuration
            st.subheader("🤖 CAPTCHA Solving")
            captcha = ad.get("captcha", {})
            captcha["enabled"] = st.toggle(
                "Enable CAPTCHA Solving",
                value=captcha.get("enabled", False),
            )
            if captcha["enabled"]:
                captcha["service"] = st.selectbox(
                    "CAPTCHA Service",
                    ["2captcha", "capmonster"],
                    index=0 if captcha.get("service", "2captcha") == "2captcha" else 1,
                )
                captcha["api_key"] = st.text_input(
                    "API Key",
                    value=captcha.get("api_key", ""),
                    type="password",
                )
                ad["captcha"] = captcha

            if st.button("💾 Save Anti-Detection Settings", type="primary"):
                config["anti_detection"] = ad
                save_config(config)
                st.success("Anti-detection settings saved!")

        # --- Scheduling Tab ---
        with tab3:
            st.subheader("⏰ Scheduled Runs")
            sched = config.get("scheduling", {})
            sched["enabled"] = st.toggle("Enable Scheduled Runs", value=sched.get("enabled", True))
            sched["cron"] = st.text_input(
                "Cron Expression (minute hour day month weekday)",
                value=sched.get("cron", "0 7 * * *"),
                help="Default: 0 7 * * * (daily at 7 AM)",
            )
            sched["interval_hours"] = st.number_input(
                "Fallback Interval (hours)",
                min_value=1, max_value=168,
                value=sched.get("interval_hours", 24),
            )
            if st.button("💾 Save Scheduling Settings", type="primary"):
                config["scheduling"] = sched
                save_config(config)
                st.success("Scheduling settings saved!")

        # --- Email Tab ---
        with tab4:
            st.subheader("📧 Email Delivery (Optional)")
            email = config.get("email", {})
            email["enabled"] = st.toggle("Enable Email Reports", value=email.get("enabled", False))

            if email["enabled"]:
                col1, col2 = st.columns(2)
                with col1:
                    email["smtp_host"] = st.text_input(
                        "SMTP Host",
                        value=email.get("smtp_host", ""),
                        placeholder="smtp.gmail.com",
                    )
                    email["smtp_port"] = st.number_input(
                        "SMTP Port",
                        min_value=1, max_value=65535,
                        value=email.get("smtp_port", 587),
                    )
                    email["smtp_user"] = st.text_input(
                        "SMTP Username",
                        value=email.get("smtp_user", ""),
                    )
                with col2:
                    email["smtp_tls"] = st.toggle("Use TLS", value=email.get("smtp_tls", True))
                    email["smtp_password"] = st.text_input(
                        "SMTP Password (app password)",
                        value=email.get("smtp_password", ""),
                        type="password",
                    )
                    email["from_address"] = st.text_input(
                        "From Address",
                        value=email.get("from_address", ""),
                    )

                recipients = email.get("to_addresses", [""])
                recips_text = "\n".join(r for r in recipients if r and r.strip())
                email["to_addresses"] = [
                    r.strip() for r in st.text_area(
                        "Recipients (one per line)",
                        value=recips_text,
                        height=80,
                    ).split("\n") if r.strip()
                ]

            if st.button("💾 Save Email Settings", type="primary"):
                config["email"] = email
                save_config(config)
                st.success("Email settings saved!")

if __name__ == "__main__":
    main_ui()