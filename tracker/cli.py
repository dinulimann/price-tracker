"""Command line entry point.

    python -m tracker init-db
    python -m tracker scrape [--max-pages N]
    python -m tracker schedule --every-hours 6
    python -m tracker export prices.csv
"""

import argparse
import asyncio
import csv
import logging
import time
from datetime import datetime, timezone

from . import alerts as alerts_mod
from . import db
from .config import settings
from .scraper import crawl

log = logging.getLogger("tracker")


def run_once(max_pages: int | None) -> None:
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    products, failed = asyncio.run(crawl(max_pages))

    with db.connect() as conn:
        previous = db.latest_snapshot(conn)
        found = alerts_mod.detect_changes(previous, products, settings.drop_threshold_pct)
        run_id = db.start_run(conn, started)
        db.save_products(conn, run_id, products)
        db.save_alerts(conn, run_id, found)
        db.finish_run(conn, run_id, datetime.now(timezone.utc), len(products), len(failed), len(found))

    alerts_mod.send(found, settings.alert_webhook_url)
    log.info(
        "run %s: %d products, %d failed, %d alerts in %.1fs",
        run_id, len(products), len(failed), len(found), time.monotonic() - t0,
    )


def export(path: str) -> None:
    with db.connect() as conn, open(path, "w", newline="") as f:
        cur = conn.execute(
            """
            SELECT p.upc, p.title, p.category, p.rating, s.price, s.stock, r.started_at
            FROM price_snapshots s
            JOIN products p ON p.upc = s.upc
            JOIN scrape_runs r ON r.id = s.run_id
            ORDER BY r.started_at, p.title
            """
        )
        w = csv.writer(f)
        w.writerow([c.name for c in cur.description])
        w.writerows(cur)
    log.info("exported to %s", path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(prog="tracker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    s = sub.add_parser("scrape")
    s.add_argument("--max-pages", type=int)
    sc = sub.add_parser("schedule")
    sc.add_argument("--every-hours", type=float, default=6)
    sc.add_argument("--max-pages", type=int)
    e = sub.add_parser("export")
    e.add_argument("path")
    args = ap.parse_args()

    if args.cmd == "init-db":
        db.init_db()
        log.info("schema ready")
    elif args.cmd == "scrape":
        run_once(args.max_pages)
    elif args.cmd == "schedule":
        while True:
            try:
                run_once(args.max_pages)
            except Exception:
                log.exception("run failed, will retry next interval")
            time.sleep(args.every_hours * 3600)
    elif args.cmd == "export":
        export(args.path)
