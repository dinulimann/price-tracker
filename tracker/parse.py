"""HTML parsing. Pure functions, so they can be tested against saved pages."""

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass
class Product:
    upc: str
    title: str
    url: str
    category: str
    price: Decimal
    stock: int
    rating: int


def parse_listing(html: str, page_url: str) -> tuple[list[str], str | None]:
    """Returns product URLs on a catalogue page and the next page URL (if any)."""
    tree = HTMLParser(html)
    links = [
        urljoin(page_url, a.attributes["href"])
        for a in tree.css("article.product_pod h3 a")
        if a.attributes.get("href")
    ]
    nxt = tree.css_first("li.next a")
    next_url = urljoin(page_url, nxt.attributes["href"]) if nxt else None
    return links, next_url


def parse_price(text: str) -> Decimal:
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned:
        raise ValueError(f"no price in {text!r}")
    return Decimal(cleaned)


def parse_stock(text: str) -> int:
    """'In stock (22 available)' -> 22, 'Out of stock' -> 0."""
    m = re.search(r"\((\d+) available\)", text)
    if m:
        return int(m.group(1))
    return 0 if "out of stock" in text.lower() else 1


def parse_product(html: str, url: str) -> Product:
    tree = HTMLParser(html)

    def text(sel: str) -> str:
        node = tree.css_first(sel)
        if node is None:
            raise ValueError(f"missing {sel} on {url}")
        return node.text(strip=True)

    table = {
        row.css_first("th").text(strip=True): row.css_first("td").text(strip=True)
        for row in tree.css("table.table-striped tr")
    }
    crumbs = [a.text(strip=True) for a in tree.css("ul.breadcrumb li a")]
    rating_node = tree.css_first("div.product_main p.star-rating")
    rating_cls = (rating_node.attributes.get("class") or "").split() if rating_node else []

    return Product(
        upc=table["UPC"],
        title=text("div.product_main h1"),
        url=url,
        category=crumbs[-1] if len(crumbs) >= 3 else "Unknown",
        price=parse_price(text("div.product_main p.price_color")),
        stock=parse_stock(text("div.product_main p.availability")),
        rating=next((RATINGS[c] for c in rating_cls if c in RATINGS), 0),
    )
