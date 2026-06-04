#!/usr/bin/env python3
"""Run Telegram bot for Paisabazaar automation."""

from __future__ import annotations

import logging
import sys

from telegram.ext import Application

from bot.config import ARTIFACTS_DIR, HEADLESS, TELEGRAM_BOT_TOKEN
from bot.handlers import register_handlers
from paisabazaar.automation import AUTOMATION_VERSION

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> int:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Set TELEGRAM_BOT_TOKEN in .env (from @BotFather)")
        return 1

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.bot_data["headless"] = HEADLESS
    app.bot_data["artifacts_dir"] = ARTIFACTS_DIR

    register_handlers(app)

    logger.info("Bot started v%s (headless=%s)", AUTOMATION_VERSION, HEADLESS)
    app.run_polling(allowed_updates=["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
