import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://tracker:tracker@localhost:5545/tracker")
    base_url: str = os.getenv("BASE_URL", "https://books.toscrape.com/")
    concurrency: int = int(os.getenv("CONCURRENCY", "8"))
    request_delay: float = float(os.getenv("REQUEST_DELAY", "0.1"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    # Alert when the price drops by at least this many percent
    drop_threshold_pct: float = float(os.getenv("DROP_THRESHOLD_PCT", "5"))
    # Slack- or Discord-compatible incoming webhook. Empty = log only.
    alert_webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")


settings = Settings()
