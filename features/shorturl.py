import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

WAIT_URL = 1


async def ask_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🔗 *קיצור URL*\nשלח את הכתובת לקיצור:", parse_mode="Markdown")
    return WAIT_URL


async def shorten(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    if not url.startswith("http"):
        url = "https://" + url
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://tinyurl.com/api-create.php?url={url}", timeout=10)
        short = resp.text.strip()
        keyboard = [
            [InlineKeyboardButton("🔗 פתח קישור", url=short)],
            [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
        ]
        await update.message.reply_text(
            f"✅ הקישור המקוצר:\n`{short}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception:
        await update.message.reply_text("❌ שגיאה בקיצור הקישור.")
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"(?i)^קיצור url$|^קצר קישור$"), ask_url)],
        states={WAIT_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, shorten)]},
        fallbacks=[],
    )
    app.add_handler(conv)
