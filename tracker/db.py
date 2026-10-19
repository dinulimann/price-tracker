from contextlib import contextmanager
from datetime import datetime

import psycopg

from .config import settings
from .parse import Product

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    upc       text PRIMARY KEY,
    title     text NOT NULL,
    url       text NOT NULL,
    category  text NOT NULL,
    rating    int  NOT NULL,
    first_seen timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id          bigserial PRIMARY KEY,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz,
    products    int,
    failed      int,
    alerts      int
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    run_id  bigint NOT NULL REFERENCES scrape_runs,
    upc     text   NOT NULL REFERENCES products,
    price   numeric(10,2) NOT NULL,
    stock   int    NOT NULL,
    PRIMARY KEY (upc, run_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id         bigserial PRIMARY KEY,
    run_id     bigint NOT NULL REFERENCES scrape_runs,
    upc        text   NOT NULL REFERENCES products,
    kind       text   NOT NULL,   -- price_drop | price_increase | back_in_stock | out_of_stock
    old_value  numeric(10,2),
    new_value  numeric(10,2),
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


@contextmanager
def connect():
    with psycopg.connect(settings.database_url) as conn:
        yield conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


def start_run(conn, started_at: datetime) -> int:
    return conn.execute(
        "INSERT INTO scrape_runs (started_at) VALUES (%s) RETURNING id", (started_at,)
    ).fetchone()[0]


def latest_snapshot(conn) -> dict[str, tuple]:
    """Last known (price, stock) per product, before the current run is saved."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (upc) upc, price, stock
        FROM price_snapshots
        ORDER BY upc, run_id DESC
        """
    ).fetchall()
    return {upc: (price, stock) for upc, price, stock in rows}


def save_products(conn, run_id: int, products: list[Product]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO products (upc, title, url, category, rating)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (upc) DO UPDATE
               SET title = EXCLUDED.title, url = EXCLUDED.url,
                   category = EXCLUDED.category, rating = EXCLUDED.rating
            """,
            [(p.upc, p.title, p.url, p.category, p.rating) for p in products],
        )
        cur.executemany(
            "INSERT INTO price_snapshots (run_id, upc, price, stock) VALUES (%s, %s, %s, %s)",
            [(run_id, p.upc, p.price, p.stock) for p in products],
        )


def save_alerts(conn, run_id: int, alerts) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO alerts (run_id, upc, kind, old_value, new_value) VALUES (%s, %s, %s, %s, %s)",
            [(run_id, a.upc, a.kind, a.old_value, a.new_value) for a in alerts],
        )


def finish_run(conn, run_id: int, finished_at: datetime, products: int, failed: int, alerts: int) -> None:
    conn.execute(
        "UPDATE scrape_runs SET finished_at = %s, products = %s, failed = %s, alerts = %s WHERE id = %s",
        (finished_at, products, failed, alerts, run_id),
    )
