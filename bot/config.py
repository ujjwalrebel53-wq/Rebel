"""Configuration: .env, then optional gitignored secrets.py (see secrets.example.py)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")

# Gitignored file — copy secrets.example.py → secrets.py and paste your token there
try:
    from bot import secrets as _secrets  # type: ignore
except ImportError:
    _secrets = None


def _from_secrets(name: str, default: str = "") -> str:
    if _secrets is None:
        return default
    val = getattr(_secrets, name, default)
    return str(val).strip() if val is not None else default


def _env_or_secrets(name: str) -> str:
    return os.getenv(name, "").strip() or _from_secrets(name)


TELEGRAM_BOT_TOKEN = _env_or_secrets("TELEGRAM_BOT_TOKEN")
HEADLESS = (
    _env_or_secrets("HEADLESS") or "true"
).lower() in ("1", "true", "yes")
ARTIFACTS_DIR = Path(_env_or_secrets("ARTIFACTS_DIR") or "artifacts")


def allowed_user_ids() -> set[int] | None:
    raw = _env_or_secrets("TELEGRAM_ALLOWED_USER_IDS")
    if not raw:
        return None
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return ids
