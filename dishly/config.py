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


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "put_your_telegram_bot_token_here":
        raise ValueError("BOT_TOKEN is missing. Copy .env.example to .env and add your token.")
    admin_id = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    try:
        admin_telegram_id = int(admin_id) if admin_id else None
    except ValueError as exc:
        raise ValueError("ADMIN_TELEGRAM_ID must be a numeric Telegram user ID.") from exc
    return Config(token, os.getenv("DATABASE_PATH", str(ROOT / "dishly.sqlite3")), admin_telegram_id)

