"""Environment configuration for the Telegram bot."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))


def allowed_user_ids() -> set[int] | None:
    """If TELEGRAM_ALLOWED_USER_IDS is set, only those users may use the bot."""
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return None
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return ids
