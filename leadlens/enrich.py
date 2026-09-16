"""Ethical, cached website enrichment.

What we collect — *business-level public info only*:
  page title, meta description, public contact email/phone on the homepage,
  social profile links, careers page presence, light tech-stack hints.

How we behave:
  * honour robots.txt (skip the site entirely if disallowed for our UA),
  * identify ourselves with a descriptive User-Agent,
  * one request per host at a time, bounded global concurrency,
  * short timeouts, no retries storms, 7-day SQLite cache so re-runs are free.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Dict, Iterable, List, Optional
from urllib import robotparser

import httpx
from bs4 import BeautifulSoup

from .models import Enrichment
from .normalize import normalize_phone
from .storage import Cache

USER_AGENT = "LeadLensBot/0.1 (+https://github.com/; lead quality research; contact via repo)"
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
SOCIAL_HOSTS = {
    "linkedin.com": "linkedin", "facebook.com": "facebook", "twitter.com": "twitter",
    "x.com": "twitter", "instagram.com": "instagram", "youtube.com": "youtube",
}
TECH_HINTS = {
    "shopify": "Shopify", "wp-content": "WordPress", "wix.com": "Wix", "squarespace": "Squarespace",
    "hubspot": "HubSpot", "gtag(": "Google Analytics", "googletagmanager": "Google Tag Manager",
    "intercom": "Intercom", "calendly": "Calendly", "stripe": "Stripe", "salesforce": "Salesforce",
    "webflow": "Webflow", "react": "React", "next/": "Next.js",
}
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def parse_html(domain: str, html: str) -> Enrichment:
    """Pure function: HTML -> Enrichment. Unit-testable without network."""
    soup = BeautifulSoup(html, "lxml")
    enr = Enrichment(domain=domain, reachable=True)
    if soup.title and soup.title.string:
        enr.title = soup.title.string.strip()[:200]
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if meta and meta.get("content"):
        enr.description = meta["content"].strip()[:400]

    text = soup.get_text(" ", strip=True)
    emails = {
        e.lower() for e in EMAIL_RE.findall(text + " " + html)
        if not e.lower().endswith(_IMAGE_EXT) and "example." not in e.lower()
    }
    for a in soup.select("a[href^='mailto:']"):
        emails.add(a["href"][7:].split("?")[0].strip().lower())
    enr.emails_found = sorted(e for e in emails if domain in e)[:5] or sorted(emails)[:3]

    phones = set()
    for a in soup.select("a[href^='tel:']"):
        p = normalize_phone(a["href"][4:])
        if p:
            phones.add(p)
    for m in PHONE_RE.finditer(text):
        p = normalize_phone(m.group())
        if p:
            phones.add(p)
    enr.phones_found = sorted(phones)[:3]

    for a in soup.select("a[href]"):
        href = a["href"].lower()
        for host, key in SOCIAL_HOSTS.items():
            if host in href and key not in enr.socials:
                enr.socials[key] = a["href"][:200]
        if any(k in href for k in ("career", "jobs", "join-us", "hiring")):
            enr.has_careers_page = True

    # Only look at loaded assets + generator meta, not body copy (avoids "we integrate with Shopify" noise).
    asset_refs = " ".join(
        [t.get("src", "") for t in soup.find_all("script")]
        + [t.get("href", "") for t in soup.find_all("link")]
        + [t.get("content", "") for t in soup.find_all("meta", attrs={"name": "generator"})]
        + [t.get_text()[:2000] for t in soup.find_all("script") if not t.get("src")]
    ).lower()
    enr.tech_hints = sorted({label for needle, label in TECH_HINTS.items() if needle in asset_refs})
    return enr


class Enricher:
    def __init__(
        self,
        cache: Optional[Cache] = None,
        timeout: float = 8.0,
        concurrency: int = 8,
        per_host_delay: float = 1.0,
        respect_robots: bool = True,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.transport = transport  # inject httpx.MockTransport in tests
        self.cache = cache
        self.timeout = timeout
        self.concurrency = concurrency
        self.per_host_delay = per_host_delay
        self.respect_robots = respect_robots
        self._robots: Dict[str, Optional[robotparser.RobotFileParser]] = {}

    async def _allowed(self, client: httpx.AsyncClient, domain: str) -> bool:
        if not self.respect_robots:
            return True
        if domain not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = await client.get(f"https://{domain}/robots.txt", timeout=self.timeout)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[domain] = rp
                else:
                    self._robots[domain] = None  # no robots -> allowed
            except Exception:
                self._robots[domain] = None
        rp = self._robots[domain]
        return True if rp is None else rp.can_fetch(USER_AGENT, f"https://{domain}/")

    async def _fetch_one(self, client: httpx.AsyncClient, sem: asyncio.Semaphore, domain: str) -> Enrichment:
        if self.cache is not None:
            hit = self.cache.get_enrichment(domain)
            if hit:
                enr = Enrichment(**hit)
                enr.from_cache = True
                return enr
        async with sem:
            if not await self._allowed(client, domain):
                enr = Enrichment(domain=domain, robots_blocked=True, error="Disallowed by robots.txt")
            else:
                enr = await self._get_page(client, domain)
                await asyncio.sleep(self.per_host_delay)
        enr.fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if self.cache is not None:
            self.cache.put_enrichment(domain, enr.model_dump())
        return enr

    async def _get_page(self, client: httpx.AsyncClient, domain: str) -> Enrichment:
        last_err: Optional[str] = None
        for url in (f"https://{domain}/", f"http://{domain}/"):
            try:
                r = await client.get(url, timeout=self.timeout)
                if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
                    enr = parse_html(domain, r.text)
                    enr.status_code = r.status_code
                    return enr
                last_err = f"HTTP {r.status_code}"
            except Exception as exc:  # DNS, TLS, timeout ...
                last_err = type(exc).__name__
        return Enrichment(domain=domain, reachable=False, error=last_err)

    async def enrich_many_async(self, domains: Iterable[str]) -> Dict[str, Enrichment]:
        domains = [d for d in dict.fromkeys(domains) if d]
        sem = asyncio.Semaphore(self.concurrency)
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, http2=False, transport=self.transport
        ) as client:
            results = await asyncio.gather(
                *(self._fetch_one(client, sem, d) for d in domains), return_exceptions=True
            )
        out: Dict[str, Enrichment] = {}
        for d, res in zip(domains, results):
            out[d] = res if isinstance(res, Enrichment) else Enrichment(domain=d, error=repr(res))
        return out

    def enrich_many(self, domains: Iterable[str]) -> Dict[str, Enrichment]:
        """Sync wrapper safe to call from Streamlit / CLI."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Inside an existing loop (e.g. Jupyter) — run in a fresh thread.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(1) as ex:
                return ex.submit(lambda: asyncio.run(self.enrich_many_async(domains))).result()
        return asyncio.run(self.enrich_many_async(domains))
