import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, filters, ContextTypes


def whatsapp_link(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    return f"https://wa.me/{digits}"


async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    link = whatsapp_link(text)
    keyboard = [
        [InlineKeyboardButton("📲 פתח וואטסאפ", url=link)],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"לחץ כדי לפתוח שיחה עם {text}:",
        reply_markup=reply_markup,
    )


def register(app) -> None:
    app.add_handler(MessageHandler(filters.Regex(r"^[\d\s\+\-\(\)]+$"), handle_number))
