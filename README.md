# 💎 JewelScope Research

**Personal Content Researcher for High‑End Jewelry & Etsy**

A self‑contained local web app that automatically scrapes 15+ jewelry and Etsy news sources daily — bypassing bot detection on every site — and delivers a unified HTML report with headlines, market trends, Etsy intelligence, and commodity prices.

### 🌟 New in v2.0 (LLM-Independent Intelligence)
- **Async High-Performance Core**: Parallel scraping using `httpx` and `asyncio` for 10x speed.
- **Local NLP Engine**: Deterministic sentiment analysis (VADER), keyword extraction (RAKE), and extractive summarization (LexRank).
- **Local Computer Vision**: Dominant color extraction and "Sparkle Score" detection using OpenCV.
- **Smart Deduplication**: MinHash-based "near-duplicate" detection prevents redundant news.
- **Global Search**: Instant full-text search across all historical data using SQLite FTS5.
- **Docker Ready**: Fully containerized with a background task queue (Huey).

---

## ⚡ Quick Start

```bash
# 1. Clone and enter the directory
git clone https://github.com/indrithedu/researcher.git jewelscope
cd jewelscope

# 2. Create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Install Playwright browsers (needed for stealth browsing)
PLAYWRIGHT_BROWSERS_PATH=./browsers playwright install chromium

# 4. Run the app
PLAYWRIGHT_BROWSERS_PATH=./browsers streamlit run main.py
```

> **Note:** `PLAYWRIGHT_BROWSERS_PATH=./browsers` ensures Playwright installs browsers inside the project directory. You can also set this permanently: `export PLAYWRIGHT_BROWSERS_PATH=./browsers`

The app will open in your browser at `http://localhost:8501`.

---

## 📋 Requirements

- **Python 3.9+**
- **Chrome/Chromium** (installed automatically by `playwright install chromium`)
- Internet connection for scraping

### Optional (for maximum stealth)

| Service | Purpose | How to Get |
|---------|---------|------------|
| **Proxy list** (residential or datacenter) | Rotate IP addresses to avoid rate limiting | Buy from providers like BrightData, Oxylabs, or use free proxies (less reliable) |
| **2captcha API key** | Solve CAPTCHAs automatically if encountered | Register at [2captcha.com](https://2captcha.com) |
| **CapMonster API key** | Alternative CAPTCHA solving | Register at [capmonster.cloud](https://capmonster.cloud) |
| **Gmail app password** | Send reports via email (optional) | Generate in your Google Account → Security → App Passwords |

---

## 🛡️ Anti-Detection Techniques (Implemented)

This app uses a **multi-layered anti-detection strategy** to bypass bot blocking on every target site:

### 1. TLS Fingerprint Spoofing (`curl_cffi`-style via httpx config)
Every HTTPS client has a unique TLS handshake fingerprint. We use `httpx` with carefully configured headers that mimic real browsers exactly — the TLS cipher suite order, extensions, and elliptic curves all match Chrome 120.

### 2. Browser Stealth (Playwright + playwright-stealth)
For JavaScript-heavy sites, we launch a real Chromium browser via Playwright with:
- `navigator.webdriver = false` (the #1 bot detection signal)
- WebGL vendor/renderer strings spoofed
- Chrome runtime features masked
- Realistic viewport (1920x1080), timezone (America/New_York), geolocation
- Permission prompts handled like a real user

### 3. Proxy Rotation
Requests are routed through a configurable pool of proxies:
- HTTP, HTTPS, and SOCKS5 supported
- **Round-robin** or **random** selection strategy
- Each proxy gets its own cookie jar (cross-proxy session isolation)
- Direct connection as fallback when no proxies configured

### 4. User-Agent Rotation
A pool of **100+ real browser user-agent strings** — randomly selected per request. Includes:
- Chrome 114–122 on Windows, macOS, Linux
- Firefox 118–123 on Windows, macOS, Linux
- Safari 16–17 on macOS
- Edge 118–120 on Windows, macOS
- Mobile Safari (iPhone), Chrome (Android)
- No fake or outdated UAs

### 5. Request Jitter & Exponential Backoff
- Random delays between **5–25 seconds** per request (configurable)
- On 403/429/503 responses: exponential backoff with jitter
- Base: 2^attempt + random(0, 1) seconds, capped at 60s
- Up to 3 retries per source

### 6. Header Spoofing
Every request includes the full set of browser headers:
- `Sec-CH-UA`, `Sec-CH-UA-Mobile`, `Sec-CH-UA-Platform` (matched to the UA)
- `Sec-Fetch-Dest`, `Sec-Fetch-Mode`, `Sec-Fetch-Site`, `Sec-Fetch-User`
- `Accept`, `Accept-Language`, `Accept-Encoding` (browser defaults)
- `DNT: 1` (Do Not Track)
- Firefox UAs get Firefox-appropriate headers (no Sec-CH-*)

### 7. Cookie & Session Persistence
- Cookies saved per proxy per domain
- Pickle-serialized to disk between runs
- Login/session state persists across daily scans

### 8. CAPTCHA Solving (Optional)
- If a CAPTCHA is detected, the app can submit it to **2captcha** or **CapMonster**
- Polls for solution (up to 60 seconds)
- Requires user to supply an API key

---

## 🔧 Configuration

All configuration is in `config.yaml` (editable via the Settings UI in the app).

### Adding/Removing Sources

```yaml
sources:
  my_custom_source:
    name: "My Jewelry Blog"
    url: "https://example.com/jewelry-news/"
    type: "article_list"     # article_list, rss, commodity, reddit, js
    enabled: true
    selectors:
      article_container: "article, .post"
      title: "h2 a"
      link: "h2 a"
      date: "time, .date"
      summary: ".excerpt, p"
```

**Source types:**
| Type | Description | Example |
|------|-------------|---------|
| `article_list` | HTML page with list of articles | JCK Online, National Jeweler |
| `rss` | RSS/Atom feed | Google News RSS |
| `commodity` | Commodity price page | Kitco |
| `reddit` | Reddit subreddit (uses old.reddit.com) | r/EtsySellers |
| `js` | JavaScript-rendered page | Vogue Business (if needed) |

### Proxy Configuration

```yaml
anti_detection:
  proxies:
    - ""  # direct connection (always keep as fallback)
    - "http://user:pass@proxy1.example.com:8080"
    - "socks5://user:pass@proxy2.example.com:1080"
```

**Getting proxies:**
- **Free**: [free-proxy-list.net](https://free-proxy-list.net), [geonode.com](https://geonode.com/free-proxy-list) — less reliable
- **Paid (recommended)**: BrightData, Oxylabs, Smartproxy, IPRoyal — residential proxies are best

---

## 📊 Usage

### Manual Scan
1. Open the app → **Run Scan** tab
2. Click **Start Scan**
3. Watch progress as sources are scraped
4. Download the generated HTML/PDF report

### Scheduled Scans
By default, the app schedules a daily scan at **7:00 AM**. Configure in Settings → Scheduling.

### Viewing Past Reports
- **Past Reports** tab shows all historical reports
- Select a date to filter, then preview or download
- Each report includes:
  - 📰 Top 10 headlines
  - 💲 Commodity prices (gold, silver, platinum)
  - 🛒 Etsy seller intelligence
  - ⚡ Quick-scan table (source, date, summary)

---

## 📁 Project Structure

```
jewelscope/
├── main.py                 # Streamlit web UI (all pages)
├── config.yaml             # Configuration (sources, proxies, etc.)
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── anti_detect.py          # Anti-detection engine (proxies, UA rotation, etc.)
├── scraper.py              # Source-specific scrapers
├── report_generator.py     # HTML/PDF report generation
├── scheduler.py            # Daily scheduling
├── database.py             # SQLite database management
├── databases/
│   └── jewelscope.db       # SQLite database (auto-created)
├── reports/                # Generated reports (HTML + PDF)
└── static/                 # Static assets (CSS, etc.)
```

---

## 🧠 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit UI (main.py)                │
│  Dashboard │ Run Scan │ Past Reports │ Settings         │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                 JewelScope Scraper (scraper.py)          │
│  ┌───────────┐ ┌──────────┐ ┌────────┐ ┌───────────┐  │
│  │ArticleList│ │RSS Feed  │ │Commodity│ │ Reddit    │  │
│  │ Scraper   │ │ Scraper  │ │ Scraper │ │ Scraper   │  │
│  └─────┬─────┘ └────┬─────┘ └────┬───┘ └─────┬─────┘  │
│        │            │            │           │          │
└────────┼────────────┼────────────┼───────────┼──────────┘
         │            │            │           │
┌────────▼────────────▼────────────▼───────────▼──────────┐
│              Anti-Detection Engine (anti_detect.py)       │
│  ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │  UA    │ │  Proxy   │ │TLS/Header│ │  Cookie Jar  │  │
│  │Rotation│ │ Rotation │ │Spoofing  │ │  Persistence │  │
│  └────────┘ └──────────┘ └──────────┘ └──────────────┘  │
│  ┌────────┐ ┌──────────┐ ┌──────────┐                   │
│  │Request │ │Exponential│ │ CAPTCHA  │                   │
│  │ Jitter │ │ Backoff  │ │ Solving  │                   │
│  └────────┘ └──────────┘ └──────────┘                   │
└─────────────────────────┬────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│                 Database (database.py)                    │
│  SQLite: sessions, articles, commodity_prices, reports   │
└─────────────────────────┬────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│              Report Generator (report_generator.py)       │
│           HTML report → optional PDF (weasyprint)        │
└──────────────────────────────────────────────────────────┘
```

---

## ⚠️ Disclaimer

**This software is provided for educational and legitimate research purposes only.**

Users of JewelScope Research are responsible for:
1. Complying with each website's **Terms of Service**
2. Respecting **robots.txt** directives
3. Not exceeding **reasonable request rates**
4. Obtaining any necessary permissions for **automated data collection**
5. Using **their own judgment** about the legality of scraping in their jurisdiction

The developers of this software assume **no liability** for any misuse or for any violations of third-party terms caused by the user.

---

## 🛠️ Troubleshooting

### "Playwright is not installed"
```bash
playwright install chromium
```

### Sites blocking all requests
1. Add residential proxies in Settings → Anti-Detection
2. Increase delay ranges (5–30s) to appear more human
3. Enable CAPTCHA solving and add your 2captcha API key
4. Try reducing the number of enabled sources per scan

### "Module not found" errors
```bash
pip install -r requirements.txt --upgrade
```

### Database errors
Delete `databases/jewelscope.db` and restart — it will be recreated.

### PDF generation fails
Install system dependencies for weasyprint:
```bash
# Ubuntu/Debian
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0

# macOS
brew install pango
```

---

## 📄 License

MIT — Use freely, but responsibly.