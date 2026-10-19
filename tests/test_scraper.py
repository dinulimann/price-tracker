from pathlib import Path

import httpx
import pytest
import respx

from tracker import scraper

FIX = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/catalogue/"


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr(scraper.asyncio, "sleep", no_sleep)


@respx.mock
async def test_crawl_one_page_retries_transient_errors_and_reports_failures():
    respx.get(BASE + "page-1.html").mock(return_value=httpx.Response(200, text=(FIX / "listing.html").read_text()))

    product_html = (FIX / "product.html").read_text()
    first = BASE + "a-light-in-the-attic_1000/index.html"
    # first product: one 503, then OK -> must be retried, not lost
    respx.get(first).mock(side_effect=[httpx.Response(503), httpx.Response(200, text=product_html)])
    # one product always 404 -> reported as failed
    broken = BASE + "tipping-the-velvet_999/index.html"
    respx.get(broken).mock(return_value=httpx.Response(404))
    # every other product page
    respx.get(url__regex=r".*/index\.html$").mock(return_value=httpx.Response(200, text=product_html))

    products, failed = await scraper.crawl(max_pages=1)

    assert len(products) == 19
    assert failed == [broken]
