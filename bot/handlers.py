"""Telegram command handlers for Paisabazaar automation."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import allowed_user_ids
from paisabazaar.automation import PaisabazaarAutomation

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)

ASK_MOBILE, ASK_OTP = range(2)

CANCEL_KEYBOARD = ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)


def _is_allowed(user_id: int) -> bool:
    allowed = allowed_user_ids()
    return allowed is None or user_id in allowed


async def _deny_if_not_allowed(update: Update) -> bool:
    user = update.effective_user
    if not user or _is_allowed(user.id):
        return False
    if update.message:
        await update.message.reply_text("You are not allowed to use this bot.")
    return True


def _get_automation(context: ContextTypes.DEFAULT_TYPE) -> PaisabazaarAutomation:
    bot_data = context.application.bot_data
    if "automation" not in bot_data:
        bot_data["automation"] = PaisabazaarAutomation(
            headless=bot_data.get("headless", True),
            artifacts_dir=bot_data.get("artifacts_dir"),
        )
    return bot_data["automation"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_allowed(update):
        return
    assert update.message
    await update.message.reply_text(
        "Paisabazaar bot — automate credit score check.\n\n"
        "Commands:\n"
        "/cibil — Free CIBIL / credit score (OTP on your phone)\n"
        "/cancel — Stop current flow\n\n"
        "Note: OTP aapke registered mobile par aayega; bot sirf browser automate karta hai.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def cibil_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_if_not_allowed(update):
        return ConversationHandler.END
    assert update.message
    context.user_data.clear()
    await update.message.reply_text(
        "10-digit mobile number bhejo (jo Paisabazaar / bank mein registered ho):",
        reply_markup=CANCEL_KEYBOARD,
    )
    return ASK_MOBILE


async def receive_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_if_not_allowed(update):
        return ConversationHandler.END
    assert update.message and update.message.text

    mobile = re.sub(r"\D", "", update.message.text)
    if len(mobile) != 10:
        await update.message.reply_text("Galat number. 10 digits bhejo, jaise 9876543210")
        return ASK_MOBILE

    await update.message.reply_text("Paisabazaar open kar raha hoon, OTP bhej raha hoon…")

    automation = _get_automation(context)
    try:
        await automation.start()
        status = await automation.submit_mobile_for_otp(mobile)
    except Exception as exc:
        logger.exception("submit_mobile failed")
        await update.message.reply_text(f"Error: {exc}")
        err_shot = Path("artifacts/otp_frame_missing.png")
        if err_shot.exists():
            with err_shot.open("rb") as photo:
                await update.message.reply_photo(
                    photo=photo, caption="Debug screenshot — site load issue"
                )
        return ConversationHandler.END

    context.user_data["mobile"] = mobile
    await update.message.reply_text(status)
    return ASK_OTP


async def receive_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_if_not_allowed(update):
        return ConversationHandler.END
    assert update.message and update.message.text

    otp = re.sub(r"\D", "", update.message.text)
    mobile = context.user_data.get("mobile", "")
    if len(otp) != 4:
        await update.message.reply_text("4-digit OTP bhejo.")
        return ASK_OTP

    await update.message.reply_text("OTP verify ho raha hai…")

    automation = _get_automation(context)
    try:
        result = await automation.submit_otp_and_fetch_score(otp, mobile)
    except Exception as exc:
        logger.exception("submit_otp failed")
        await update.message.reply_text(f"OTP fail: {exc}\n/cibil se dubara try karo.")
        return ConversationHandler.END

    await update.message.reply_text(result.message, parse_mode="Markdown")
    if result.screenshot_path and result.screenshot_path.exists():
        with result.screenshot_path.open("rb") as photo:
            await update.message.reply_photo(photo=photo, caption="Dashboard screenshot")

    await update.message.reply_text("Done. /cibil for another check.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def register_handlers(application: Application) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler("cibil", cibil_start)],
        states={
            ASK_MOBILE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_mobile),
            ],
            ASK_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_otp),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(conv)
