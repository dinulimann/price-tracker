from decimal import Decimal
from pathlib import Path

import pytest

from tracker.parse import parse_listing, parse_price, parse_product, parse_stock

FIX = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/catalogue/"


def test_listing_returns_20_links_and_next_page():
    links, nxt = parse_listing((FIX / "listing.html").read_text(), BASE + "page-1.html")
    assert len(links) == 20
    assert links[0] == BASE + "a-light-in-the-attic_1000/index.html"
    assert nxt == BASE + "page-2.html"


def test_last_listing_page_has_no_next():
    _, nxt = parse_listing((FIX / "listing_last.html").read_text(), BASE + "page-50.html")
    assert nxt is None


def test_product_page():
    url = BASE + "a-light-in-the-attic_1000/index.html"
    p = parse_product((FIX / "product.html").read_text(), url)
    assert p.upc == "a897fe39b1053632"
    assert p.title == "A Light in the Attic"
    assert p.category == "Poetry"
    assert p.price == Decimal("51.77")
    assert p.stock == 22
    assert p.rating == 3


@pytest.mark.parametrize("text,expected", [
    ("In stock (22 available)", 22),
    ("Out of stock", 0),
    ("In stock", 1),
])
def test_parse_stock(text, expected):
    assert parse_stock(text) == expected


def test_parse_price_handles_currency_and_mojibake():
    assert parse_price("£51.77") == Decimal("51.77")
    assert parse_price("Â£9.00") == Decimal("9.00")
    with pytest.raises(ValueError):
        parse_price("n/a")
