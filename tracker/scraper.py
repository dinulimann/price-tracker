"""Async crawler: follows catalogue pagination, then fetches product pages
concurrently with a semaphore, a small delay and retries with backoff."""

import asyncio
import logging
import random
from urllib.parse import urljoin

import httpx

from .config import settings
from .parse import Product, parse_listing, parse_product

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "price-tracker/1.0 (portfolio project; contact via GitHub)"}
RETRY_STATUS = {429, 500, 502, 503, 504}


async def fetch(client: httpx.AsyncClient, url: str) -> str:
    for attempt in range(1, settings.max_retries + 1):
        try:
            resp = await client.get(url)
            if resp.status_code in RETRY_STATUS:
                raise httpx.HTTPStatusError(f"status {resp.status_code}", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.text
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt == settings.max_retries:
                raise
            wait = 2 ** attempt + random.random()
            log.warning("retry %s/%s for %s in %.1fs (%s)", attempt, settings.max_retries, url, wait, exc)
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")


async def crawl(max_pages: int | None = None) -> tuple[list[Product], list[str]]:
    """Returns the scraped products and the URLs that failed."""
    products: list[Product] = []
    failed: list[str] = []
    sem = asyncio.Semaphore(settings.concurrency)

    async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        # 1. Walk the catalogue pages to collect product URLs
        urls: list[str] = []
        page_url: str | None = urljoin(settings.base_url, "catalogue/page-1.html")
        pages = 0
        while page_url and (max_pages is None or pages < max_pages):
            html = await fetch(client, page_url)
            links, page_url = parse_listing(html, page_url)
            urls.extend(links)
            pages += 1
        log.info("found %d products on %d pages", len(urls), pages)

        # 2. Fetch product pages concurrently
        async def one(url: str) -> None:
            async with sem:
                try:
                    products.append(parse_product(await fetch(client, url), url))
                except Exception as exc:  # keep going; report at the end
                    log.error("failed %s: %s", url, exc)
                    failed.append(url)
                await asyncio.sleep(settings.request_delay)

        await asyncio.gather(*(one(u) for u in urls))

    return products, failed
