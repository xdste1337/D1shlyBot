from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_path: str
    admin_telegram_id: int | None
    deepseek_api_key: str
    deepseek_model: str
    plus_monthly_stars: int
    advisor_daily_limit: int


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "put_your_telegram_bot_token_here":
        raise ValueError("BOT_TOKEN is missing. Copy .env.example to .env and add your token.")
    admin_id = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    try:
        admin_telegram_id = int(admin_id) if admin_id else None
    except ValueError as exc:
        raise ValueError("ADMIN_TELEGRAM_ID must be a numeric Telegram user ID.") from exc
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
    raw_price = os.getenv("PLUS_MONTHLY_STARS", "").strip()
    try:
        price = int(raw_price) if raw_price else 0
        daily_limit = int(os.getenv("ADVISOR_DAILY_LIMIT", "10"))
    except ValueError as exc:
        raise ValueError("PLUS_MONTHLY_STARS and ADVISOR_DAILY_LIMIT must be integers.") from exc
    if price < 0 or price > 10000:
        raise ValueError("PLUS_MONTHLY_STARS must be between 1 and 10000, or empty to disable payments.")
    if daily_limit < 1 or daily_limit > 100:
        raise ValueError("ADVISOR_DAILY_LIMIT must be between 1 and 100.")
    return Config(
        token,
        os.getenv("DATABASE_PATH", str(ROOT / "dishly.sqlite3")),
        admin_telegram_id,
        api_key,
        model,
        price,
        daily_limit,
    )

