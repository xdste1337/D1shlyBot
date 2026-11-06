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


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "put_your_telegram_bot_token_here":
        raise ValueError("BOT_TOKEN is missing. Copy .env.example to .env and add your token.")
    return Config(token, os.getenv("DATABASE_PATH", str(ROOT / "dishly.sqlite3")))

