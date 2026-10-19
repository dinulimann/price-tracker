from decimal import Decimal

from tracker.alerts import detect_changes
from tracker.parse import Product


def product(upc, price, stock=5):
    return Product(upc=upc, title=f"Book {upc}", url=f"https://x/{upc}", category="Poetry",
                   price=Decimal(price), stock=stock, rating=3)


def kinds(alerts):
    return sorted((a.upc, a.kind) for a in alerts)


def test_drop_over_threshold_alerts_but_small_drop_does_not():
    prev = {"a": (Decimal("20.00"), 5), "b": (Decimal("20.00"), 5)}
    cur = [product("a", "18.00"), product("b", "19.50")]   # -10% and -2.5%
    assert kinds(detect_changes(prev, cur, drop_threshold_pct=5)) == [("a", "price_drop")]


def test_increase_and_stock_changes():
    prev = {"a": (Decimal("10.00"), 0), "b": (Decimal("10.00"), 3), "c": (Decimal("10.00"), 3)}
    cur = [product("a", "10.00", stock=4), product("b", "10.00", stock=0), product("c", "12.00")]
    assert kinds(detect_changes(prev, cur, 5)) == [
        ("a", "back_in_stock"), ("b", "out_of_stock"), ("c", "price_increase"),
    ]


def test_new_products_and_unchanged_do_not_alert():
    prev = {"a": (Decimal("10.00"), 3)}
    cur = [product("a", "10.00", stock=3), product("new", "1.00")]
    assert detect_changes(prev, cur, 5) == []


def test_message_shows_percentage():
    a = detect_changes({"a": (Decimal("20.00"), 5)}, [product("a", "15.00")], 5)[0]
    assert "-25.0%" in a.message()
