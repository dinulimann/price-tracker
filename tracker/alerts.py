"""Change detection between the previous and the current scrape, plus
delivery to a Slack/Discord-style webhook."""

import logging
from dataclasses import dataclass
from decimal import Decimal

import httpx

from .parse import Product

log = logging.getLogger(__name__)


@dataclass
class Alert:
    upc: str
    title: str
    kind: str
    old_value: Decimal | None
    new_value: Decimal | None
    url: str

    def message(self) -> str:
        if self.kind == "price_drop":
            pct = (self.old_value - self.new_value) / self.old_value * 100
            return f"📉 {self.title}: £{self.old_value} → £{self.new_value} (-{pct:.1f}%) {self.url}"
        if self.kind == "price_increase":
            return f"📈 {self.title}: £{self.old_value} → £{self.new_value} {self.url}"
        if self.kind == "back_in_stock":
            return f"✅ Back in stock: {self.title} ({self.new_value:.0f} available) {self.url}"
        return f"⚠️ Out of stock: {self.title} {self.url}"


def detect_changes(previous: dict[str, tuple], current: list[Product], drop_threshold_pct: float) -> list[Alert]:
    """previous maps upc -> (price, stock) from the last run. New products never alert."""
    alerts: list[Alert] = []
    for p in current:
        if p.upc not in previous:
            continue
        old_price, old_stock = previous[p.upc]
        old_price = Decimal(old_price)

        if p.price < old_price:
            drop_pct = (old_price - p.price) / old_price * 100
            if drop_pct >= Decimal(str(drop_threshold_pct)):
                alerts.append(Alert(p.upc, p.title, "price_drop", old_price, p.price, p.url))
        elif p.price > old_price:
            alerts.append(Alert(p.upc, p.title, "price_increase", old_price, p.price, p.url))

        if old_stock == 0 and p.stock > 0:
            alerts.append(Alert(p.upc, p.title, "back_in_stock", Decimal(old_stock), Decimal(p.stock), p.url))
        elif old_stock > 0 and p.stock == 0:
            alerts.append(Alert(p.upc, p.title, "out_of_stock", Decimal(old_stock), Decimal(0), p.url))
    return alerts


def send(alerts: list[Alert], webhook_url: str) -> None:
    for a in alerts:
        log.info("ALERT %s", a.message())
    if not webhook_url or not alerts:
        return
    lines = [a.message() for a in alerts[:20]]
    if len(alerts) > 20:
        lines.append(f"…and {len(alerts) - 20} more")
    text = "\n".join(lines)
    # "text" is read by Slack, "content" by Discord
    resp = httpx.post(webhook_url, json={"text": text, "content": text[:2000]}, timeout=10)
    resp.raise_for_status()
