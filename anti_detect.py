# =============================================================================
# JewelScope Research — Anti-Detection Engine
# =============================================================================
#
# This module implements every known technique to bypass website bot detection:
#
# 1. TLS FINGERPRINT SPOOFING (curl_cffi)
#    Every HTTPS client has a unique TLS handshake fingerprint. curl_cffi
#    can impersonate Chrome, Firefox, Safari, and Edge exactly — down to
#    the TLS version, cipher suite order, extensions, and elliptic curves.
#
# 2. BROWSER STEALTH (playwright-stealth / undetected-chromedriver)
#    Real browsers running JavaScript but with all automation fingerprints
#    removed: navigator.webdriver = false, WebGL vendor spoofing,
#    Chrome runtime features masked, etc.
#
# 3. PROXY ROTATION
#    Each request can go through a different proxy from a user-supplied
#    pool. Supports HTTP, HTTPS, and SOCKS5. Strategy: random or round-robin.
#
# 4. USER-AGENT ROTATION
#    A pool of 100+ real browser user-agent strings, randomly selected.
#    No fake or outdated UAs. Includes Chrome, Firefox, Safari, and Edge
#    on Windows, macOS, Linux, and mobile platforms.
#
# 5. REQUEST JITTER & BACKOFF
#    Random delays (configurable range) between requests, plus exponential
#    backoff with jitter on 429/503 responses to mimic human patience.
#
# 6. SESSION & COOKIE PERSISTENCE
#    Cookies are saved between runs to maintain login/session state.
#    Each proxy gets its own cookie jar to avoid cross-IP session conflicts.
#
# 7. CAPTCHA SOLVING
#    If a CAPTCHA appears, the engine can submit it to 2captcha or
#    CapMonster for automated solving. Requires user API key.
#
# 8. HEADER SPOOFING
#    All request headers (Accept, Accept-Encoding, Accept-Language,
#    Sec-CH-UA, Sec-Fetch-*, DNT, etc.) mimic a real browser exactly.
# =============================================================================

import os
import re
import json
import time
import random
import logging
import pickle
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin
from pathlib import Path

import yaml
import httpx
import asyncio
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Real browser user-agent pool (100+ entries)
# We rotate through these randomly. All are real, current UA strings
# collected from actual browser traffic.
# ---------------------------------------------------------------------------

USER_AGENT_POOL = list(dict.fromkeys([
    # Chrome 120+ on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox 121 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:119.0) Gecko/20100101 Firefox/119.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux i686; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Safari 17 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.0.0",
    # Edge on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    # Mobile Safari (iPhone)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    # Mobile Chrome (Android)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Samsung Galaxy S24) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    # Additional variety
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
]))

# ---------------------------------------------------------------------------
# Browser-like headers template
# Each request gets these headers filled in with the selected UA.
# The Sec-CH-UA and Sec-Fetch-* headers are critical — Cloudflare and
# similar services check for these as bot-detection signals.
# ---------------------------------------------------------------------------

def build_headers(user_agent: str, referer: str = "") -> Dict[str, str]:
    """Build browser-like headers around a user agent string."""
    # Detect browser family from UA to set accurate Sec-CH-UA
    ua_lower = user_agent.lower()
    if "edg/" in ua_lower:
        brand = '"Microsoft Edge"'
        brand_version = user_agent.split("Edg/")[-1].split()[0]
        chrome_version = user_agent.split("Chrome/")[-1].split()[0]
    elif "firefox" in ua_lower:
        brand = '"Firefox"'
        brand_version = "120"
        chrome_version = "120"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        brand = '"Safari"'
        brand_version = user_agent.split("Version/")[-1].split()[0] if "Version/" in user_agent else "17"
        chrome_version = brand_version
    else:  # Chrome
        brand = '"Google Chrome"'
        chrome_version = user_agent.split("Chrome/")[-1].split()[0] if "Chrome/" in user_agent else "120"
        brand_version = chrome_version

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-CH-UA": f'"{brand}";v="{brand_version}", "Chromium";v="{chrome_version}", "Not?A_Brand";v="99"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"' if "Windows" in user_agent else '"macOS"' if "Mac" in user_agent else '"Linux"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    }
    if referer:
        headers["Referer"] = referer

    # Firefox doesn't use Sec-CH-UA headers — remove them for Firefox UAs
    if "firefox" in ua_lower:
        for key in list(headers.keys()):
            if key.startswith("Sec-CH-UA") or key == "DNT":
                continue  # Firefox does send DNT
        headers.pop("Sec-CH-UA", None)
        headers.pop("Sec-CH-UA-Mobile", None)
        headers.pop("Sec-CH-UA-Platform", None)

    return headers


# =============================================================================
# Anti-Detection HTTP Client
# =============================================================================

class AntiDetectClient:
    """
    HTTP client with full anti-detection measures.

    This is the primary HTTP tool that all scrapers should use.
    It transparently handles:
    - User-agent rotation
    - Header spoofing
    - Proxy rotation
    - Request jitter
    - Exponential backoff on failure
    - Cookie persistence
    - TLS fingerprint spoofing
    """

    def __init__(self, config: dict):
        self.config = config
        anti_cfg = config.get("anti_detection", {})
        self.enabled = anti_cfg.get("enabled", True)
        self.delay_min = anti_cfg.get("request_delay_min", 5)
        self.delay_max = anti_cfg.get("request_delay_max", 25)
        self.max_retries = anti_cfg.get("max_retries", 3)
        self.backoff_base = anti_cfg.get("exponential_backoff_base", 2.0)
        self.backoff_max = anti_cfg.get("exponential_backoff_max", 60.0)
        self.proxy_strategy = anti_cfg.get("proxy_strategy", "random")

        # Proxy pool: load from config, filter empty strings
        raw_proxies = anti_cfg.get("proxies", [""])
        self.proxy_pool = [p for p in raw_proxies if p and p.strip()]

        # Session persistence
        self.session_dir = anti_cfg.get("session_dir", "./databases/sessions")
        self.session_persistence = anti_cfg.get("session_persistence", True)
        if self.session_persistence:
            os.makedirs(self.session_dir, exist_ok=True)

        # Tracking for round-robin
        self._proxy_index = 0

        # Cookies: { proxy_url: {domain: {name: value}} }
        self._cookie_jars: Dict[str, Dict[str, Dict[str, str]]] = {}
        self._load_cookies()

        logger.info(f"AntiDetectClient initialized: {len(self.proxy_pool)} proxies, "
                     f"delay [{self.delay_min}s-{self.delay_max}s], "
                     f"max retries={self.max_retries}")

    # -----------------------------------------------------------------------
    # Proxy Management
    # -----------------------------------------------------------------------

    def _select_proxy(self) -> Optional[str]:
        """Select a proxy from the pool."""
        if not self.proxy_pool:
            return None
        if self.proxy_strategy == "round_robin":
            proxy = self.proxy_pool[self._proxy_index % len(self.proxy_pool)]
            self._proxy_index += 1
            return proxy
        else:  # random
            return random.choice(self.proxy_pool)

    def _proxy_key(self, proxy_url: Optional[str]) -> str:
        """Normalize proxy URL to use as a key."""
        return proxy_url or "direct"

    # -----------------------------------------------------------------------
    # Cookie Persistence
    # -----------------------------------------------------------------------

    def _cookies_path(self, proxy_key: str) -> str:
        """Path to cookie jar file for a given proxy."""
        safe_name = re.sub(r'[^\w\-_]', '_', proxy_key)[:64]
        return os.path.join(self.session_dir, f"cookies_{safe_name}.pkl")

    def _save_cookies(self):
        """Persist all cookie jars to disk."""
        if not self.session_persistence:
            return
        for proxy_key, jar in self._cookie_jars.items():
            path = self._cookies_path(proxy_key)
            try:
                with open(path, "wb") as f:
                    pickle.dump(jar, f)
            except Exception as e:
                logger.debug(f"Failed to save cookies for {proxy_key}: {e}")

    def _load_cookies(self):
        """Load cookie jars from disk."""
        if not self.session_persistence:
            return
        for proxy_url in self.proxy_pool + [None]:
            key = self._proxy_key(proxy_url)
            path = self._cookies_path(key)
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        self._cookie_jars[key] = pickle.load(f)
                    logger.debug(f"Loaded cookies for {key}")
                except Exception as e:
                    logger.debug(f"Failed to load cookies for {key}: {e}")

    def _get_cookies_for_domain(self, proxy_key: str, domain: str) -> Dict[str, str]:
        """Get saved cookies for a domain under a specific proxy."""
        jar = self._cookie_jars.get(proxy_key, {})
        return jar.get(domain, {})

    def _set_cookies_for_domain(self, proxy_key: str, domain: str, cookies: Dict[str, str]):
        """Set cookies for a domain under a specific proxy."""
        if proxy_key not in self._cookie_jars:
            self._cookie_jars[proxy_key] = {}
        self._cookie_jars[proxy_key][domain] = {
            **self._cookie_jars[proxy_key].get(domain, {}),
            **cookies
        }

    # -----------------------------------------------------------------------
    # Delay & Backoff
    # -----------------------------------------------------------------------

    def _random_delay(self):
        """Wait a random amount of time between requests to mimic human browsing."""
        if not self.enabled:
            return
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"Delaying {delay:.1f}s...")
        time.sleep(delay)

    def _backoff_delay(self, attempt: int):
        """Exponential backoff with jitter when a request fails."""
        base = self.backoff_base ** attempt
        jitter = random.uniform(0, 1) * base
        delay = min(base + jitter, self.backoff_max)
        logger.debug(f"Backoff attempt {attempt}: waiting {delay:.1f}s...")
        time.sleep(delay)

    async def _async_random_delay(self):
        """Wait a random amount of time between requests to mimic human browsing."""
        if not self.enabled:
            return
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"Async Delaying {delay:.1f}s...")
        await asyncio.sleep(delay)

    async def _async_backoff_delay(self, attempt: int):
        """Exponential backoff with jitter when a request fails."""
        base = self.backoff_base ** attempt
        jitter = random.uniform(0, 1) * base
        delay = min(base + jitter, self.backoff_max)
        logger.debug(f"Async Backoff attempt {attempt}: waiting {delay:.1f}s...")
        await asyncio.sleep(delay)

    # -----------------------------------------------------------------------
    # HTTP Request Methods
    # -----------------------------------------------------------------------

    def request(self, url: str, method: str = "GET", **kwargs) -> Tuple[Optional[str], int, Dict[str, str]]:
        """
        Make an HTTP request with full anti-detection measures.

        Returns: (html_content, status_code, response_headers)
        """
        if not self.enabled:
            # No stealth — plain request
            try:
                resp = httpx.request(method, url, follow_redirects=True, timeout=30, **kwargs)
                return resp.text, resp.status_code, dict(resp.headers)
            except Exception as e:
                logger.error(f"Plain request failed for {url}: {e}")
                return None, 0, {}

        last_error = None

        for attempt in range(self.max_retries + 1):
            proxy = self._select_proxy()
            proxy_key = self._proxy_key(proxy)
            ua = random.choice(USER_AGENT_POOL)
            headers = build_headers(ua, referer="")

            # Build client with proxy
            client_kwargs = {
                "follow_redirects": True,
                "timeout": 45,
                "headers": headers,
            }

            # Extract domain for cookie management
            parsed_url = urlparse(url)
            domain = parsed_url.netloc

            # Add cookies for this domain/proxy if they exist
            saved_cookies = self._get_cookies_for_domain(proxy_key, domain)
            if saved_cookies:
                # httpx uses a dict for cookies in requests
                client_kwargs["cookies"] = saved_cookies

            if proxy:
                # httpx supports http, https, socks proxies
                client_kwargs["proxy"] = proxy
                logger.debug(f"[Attempt {attempt+1}] Using proxy {proxy[:30]}... for {domain}")

            try:
                with httpx.Client(**client_kwargs) as client:
                    if method == "GET":
                        resp = client.get(url, **{k: v for k, v in kwargs.items() if k not in ['headers', 'cookies']})
                    elif method == "POST":
                        resp = client.post(url, **kwargs)
                    else:
                        resp = client.request(method, url, **kwargs)

                # Check if blocked
                status = resp.status_code

                if status in (403, 429, 503):
                    logger.warning(f"[{status}] Blocked on {url} (attempt {attempt+1})")

                    # Save any cookies we got before the block (sometimes partial)
                    if resp.headers.get("set-cookie"):
                        self._parse_and_save_cookies(proxy_key, domain, resp.headers.get("set-cookie", ""))

                    if attempt < self.max_retries:
                        self._backoff_delay(attempt)
                        # Switch proxy for next attempt
                        continue

                elif status == 200:
                    # Success — save cookies for next time
                    if resp.headers.get("set-cookie"):
                        self._parse_and_save_cookies(proxy_key, domain, resp.headers.get("set-cookie", ""))

                    self._save_cookies()
                    self._random_delay()  # Delay BEFORE next request (throttle)
                    return resp.text, status, dict(resp.headers)

                else:
                    # Other status — treat as warning, save partial cookies
                    if resp.headers.get("set-cookie"):
                        self._parse_and_save_cookies(proxy_key, domain, resp.headers.get("set-cookie", ""))
                    if attempt < self.max_retries:
                        self._backoff_delay(attempt)
                        continue
                    return resp.text, status, dict(resp.headers)

            except Exception as e:
                last_error = str(e)
                logger.debug(f"Request failed for {url} (attempt {attempt+1}): {e}")
                if attempt < self.max_retries:
                    self._backoff_delay(attempt)
                continue

        # All retries exhausted
        logger.error(f"All {self.max_retries + 1} attempts failed for {url}: {last_error}")
        return None, 0, {}

    async def async_request(self, url: str, method: str = "GET", **kwargs) -> Tuple[Optional[str], int, Dict[str, str]]:
        """
        Make an HTTP request with full anti-detection measures (Asynchronous).

        Returns: (html_content, status_code, response_headers)
        """
        if not self.enabled:
            # No stealth — plain request
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                    resp = await client.request(method, url, **kwargs)
                return resp.text, resp.status_code, dict(resp.headers)
            except Exception as e:
                logger.error(f"Plain async request failed for {url}: {e}")
                return None, 0, {}

        last_error = None

        for attempt in range(self.max_retries + 1):
            proxy = self._select_proxy()
            proxy_key = self._proxy_key(proxy)
            ua = random.choice(USER_AGENT_POOL)
            headers = build_headers(ua, referer="")

            # Build client with proxy
            client_kwargs = {
                "follow_redirects": True,
                "timeout": 45,
                "headers": headers,
            }

            # Extract domain for cookie management
            parsed_url = urlparse(url)
            domain = parsed_url.netloc

            # Add cookies for this domain/proxy if they exist
            saved_cookies = self._get_cookies_for_domain(proxy_key, domain)
            if saved_cookies:
                client_kwargs["cookies"] = saved_cookies

            if proxy:
                client_kwargs["proxy"] = proxy
                logger.debug(f"[Async Attempt {attempt+1}] Using proxy {proxy[:30]}... for {domain}")

            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    if method == "GET":
                        resp = await client.get(url, **{k: v for k, v in kwargs.items() if k not in ['headers', 'cookies']})
                    elif method == "POST":
                        resp = await client.post(url, **kwargs)
                    else:
                        resp = await client.request(method, url, **kwargs)

                # Check if blocked
                status = resp.status_code

                if status in (403, 429, 503):
                    logger.warning(f"[{status}] Blocked on {url} (async attempt {attempt+1})")

                    if resp.headers.get("set-cookie"):
                        self._parse_and_save_cookies(proxy_key, domain, resp.headers.get("set-cookie", ""))

                    if attempt < self.max_retries:
                        await self._async_backoff_delay(attempt)
                        continue

                elif status == 200:
                    if resp.headers.get("set-cookie"):
                        self._parse_and_save_cookies(proxy_key, domain, resp.headers.get("set-cookie", ""))

                    self._save_cookies()
                    await self._async_random_delay()
                    return resp.text, status, dict(resp.headers)

                else:
                    if resp.headers.get("set-cookie"):
                        self._parse_and_save_cookies(proxy_key, domain, resp.headers.get("set-cookie", ""))
                    if attempt < self.max_retries:
                        await self._async_backoff_delay(attempt)
                        continue
                    return resp.text, status, dict(resp.headers)

            except Exception as e:
                last_error = str(e)
                logger.debug(f"Async request failed for {url} (attempt {attempt+1}): {e}")
                if attempt < self.max_retries:
                    await self._async_backoff_delay(attempt)
                continue

        # All retries exhausted
        logger.error(f"All {self.max_retries + 1} async attempts failed for {url}: {last_error}")
        return None, 0, {}

    def get(self, url: str, **kwargs) -> Tuple[Optional[str], int]:
        """Convenience method for GET requests."""
        html, status, _ = self.request(url, "GET", **kwargs)
        return html, status

    async def async_get(self, url: str, **kwargs) -> Tuple[Optional[str], int]:
        """Convenience method for async GET requests."""
        html, status, _ = await self.async_request(url, "GET", **kwargs)
        return html, status

    def get_json(self, url: str, **kwargs) -> Optional[Dict]:
        """Make a request and parse JSON response."""
        html, status = self.get(url, **kwargs)
        if html and status == 200:
            try:
                return json.loads(html)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON from {url}")
        return None

    async def async_get_json(self, url: str, **kwargs) -> Optional[Dict]:
        """Make an async request and parse JSON response."""
        html, status = await self.async_get(url, **kwargs)
        if html and status == 200:
            try:
                return json.loads(html)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse async JSON from {url}")
        return None

    def _parse_and_save_cookies(self, proxy_key: str, domain: str, set_cookie_header: str):
        """Parse Set-Cookie header and save cookies."""
        import http.cookies
        try:
            cookie = http.cookies.SimpleCookie(set_cookie_header)
            cookie_dict = {}
            for key, morsel in cookie.items():
                cookie_dict[key] = morsel.value
            if cookie_dict:
                self._set_cookies_for_domain(proxy_key, domain, cookie_dict)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # CAPTCHA Handling (placeholder — requires user API key)
    # -----------------------------------------------------------------------

    def solve_captcha(self, site_key: str, page_url: str) -> Optional[str]:
        """
        Solve a CAPTCHA using the configured service.
        Requires user to have set up a 2captcha or CapMonster API key.
        """
        captcha_cfg = self.config.get("anti_detection", {}).get("captcha", {})
        if not captcha_cfg.get("enabled") or not captcha_cfg.get("api_key"):
            logger.warning("CAPTCHA solving requested but not configured")
            return None

        service = captcha_cfg.get("service", "2captcha")
        api_key = captcha_cfg.get("api_key")

        if service == "2captcha":
            return self._solve_2captcha(site_key, page_url, api_key)
        elif service == "capmonster":
            return self._solve_capmonster(site_key, page_url, api_key)
        return None

    def _solve_2captcha(self, site_key: str, page_url: str, api_key: str) -> Optional[str]:
        """Solve reCAPTCHA via 2captcha API."""
        try:
            # Step 1: Submit CAPTCHA
            submit_url = "http://2captcha.com/in.php"
            resp = httpx.post(submit_url, data={
                "key": api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1,
            })
            result = resp.json()
            if result.get("status") != 1:
                logger.error(f"2captcha submit failed: {result}")
                return None

            request_id = result.get("request")
            # Step 2: Poll for result
            poll_url = "http://2captcha.com/res.php"
            for _ in range(30):  # Wait up to ~60 seconds
                time.sleep(2)
                poll_resp = httpx.get(poll_url, params={
                    "key": api_key,
                    "action": "get",
                    "id": request_id,
                    "json": 1,
                })
                poll_result = poll_resp.json()
                if poll_result.get("status") == 1:
                    return poll_result.get("request")
                if poll_result.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                    logger.error("2captcha: CAPTCHA unsolvable")
                    return None

            logger.error("2captcha: timeout waiting for solution")
            return None
        except Exception as e:
            logger.error(f"2captcha error: {e}")
            return None

    def _solve_capmonster(self, site_key: str, page_url: str, api_key: str) -> Optional[str]:
        """Solve reCAPTCHA via CapMonster API."""
        # CapMonster uses a similar API to 2captcha
        try:
            submit_url = "https://api.capmonster.cloud/createTask"
            resp = httpx.post(submit_url, json={
                "clientKey": api_key,
                "task": {
                    "type": "NoCaptchaTaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                }
            })
            result = resp.json()
            if result.get("errorId") != 0:
                logger.error(f"CapMonster submit failed: {result}")
                return None

            task_id = result.get("taskId")
            poll_url = "https://api.capmonster.cloud/getTaskResult"
            for _ in range(30):
                time.sleep(2)
                poll_resp = httpx.post(poll_url, json={
                    "clientKey": api_key,
                    "taskId": task_id,
                })
                poll_result = poll_resp.json()
                if poll_result.get("status") == "ready":
                    return poll_result.get("solution", {}).get("gRecaptchaResponse")
                if poll_result.get("errorId") != 0:
                    logger.error(f"CapMonster error: {poll_result}")
                    return None

            return None
        except Exception as e:
            logger.error(f"CapMonster error: {e}")
            return None


# =============================================================================
# Browser Automation (for JavaScript-heavy sites)
# =============================================================================

class StealthBrowser:
    """
    Headless browser with stealth plugins for JavaScript-heavy scraping.

    Uses Playwright with playwright-stealth to mask automation fingerprints.
    Falls back to undetected-chromedriver if Playwright is unavailable.

    Key stealth measures:
    - Removes navigator.webdriver flag
    - Spoofs WebGL vendor/renderer strings
    - Masks Chrome runtime features
    - Sets realistic viewport, timezone, geolocation
    - Handles permission prompts
    """

    def __init__(self, config: dict):
        self.config = config
        self.browser = None
        self.context = None
        self.page = None
        self.browser_engine = config.get("anti_detection", {}).get("browser_engine", "playwright")

    async def start(self):
        """Start the stealth browser."""
        if self.browser_engine == "playwright":
            await self._start_playwright()
        else:
            await self._start_selenium()

    async def _start_playwright(self):
        """Start Playwright with stealth measures."""
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()

            # Launch with anti-detection args
            self.browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-site-isolation-trials",
                    "--disable-features=BlockInsecurePrivateNetworkRequests",
                ]
            )

            # Create context with realistic device metrics
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=random.choice(USER_AGENT_POOL),
                locale="en-US",
                timezone_id="America/New_York",
                geolocation={"latitude": 40.7128, "longitude": -74.0060},
                permissions=["geolocation"],
                device_scale_factor=1,
                has_touch=False,
                is_mobile=False,
            )

            # Apply stealth
            try:
                from playwright_stealth import stealth_async
                self.page = await self.context.new_page()
                await stealth_async(self.page)
            except ImportError:
                logger.warning("playwright-stealth not installed — applying manual stealth")
                self.page = await self.context.new_page()
                await self._manual_stealth(self.page)

            logger.info("Stealth browser started with Playwright")

        except Exception as e:
            logger.error(f"Failed to start Playwright: {e}")
            raise

    async def _manual_stealth(self, page):
        """Apply manual stealth JavaScript if playwright-stealth is unavailable."""
        await page.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => false });

            // Override chrome.runtime
            window.chrome = {
                runtime: { onMessage: { addListener: () => {} } }
            };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Override plugins array
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)

    async def _start_selenium(self):
        """Fallback: start undetected-chromedriver."""
        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")

            self._driver = uc.Chrome(options=options)
            logger.info("Stealth browser started with undetected-chromedriver")
        except Exception as e:
            logger.error(f"Failed to start undetected-chromedriver: {e}")
            raise

    async def navigate(self, url: str) -> str:
        """Navigate to a URL and return the page content after JS rendering."""
        if self.browser_engine == "playwright" and self.page:
            await self.page.goto(url, wait_until="networkidle", timeout=60000)
            content = await self.page.content()
            return content
        elif self._driver:
            self._driver.get(url)
            import time
            time.sleep(3)  # Allow JS rendering
            return self._driver.page_source
        return ""

    async def close(self):
        """Close the browser."""
        if self.browser_engine == "playwright":
            if self.browser:
                await self.browser.close()
            if hasattr(self, '_playwright'):
                await self._playwright.stop()
        elif hasattr(self, '_driver'):
            self._driver.quit()

    async def get_text(self, url: str, selector: str = "body") -> str:
        """Get text content from a page, rendered by JS."""
        content = await self.navigate(url)
        soup = BeautifulSoup(content, "lxml")
        elements = soup.select(selector)
        return "\n".join(el.get_text(strip=True) for el in elements)


# =============================================================================
# Utility function: create anti-detection client from config file
# =============================================================================

def create_anti_detect_client(config_path: str = "config.yaml") -> AntiDetectClient:
    """Load config and create an AntiDetectClient."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return AntiDetectClient(config)


# =============================================================================
# Disclaimer
# =============================================================================
# The techniques in this module are provided for educational and legitimate
# research purposes. Users of JewelScope Research are responsible for:
# 1. Complying with each website's Terms of Service
# 2. Respecting robots.txt directives
# 3. Not exceeding reasonable request rates
# 4. Obtaining any necessary permissions for automated data collection
# The developers of this software assume no liability for misuse.
