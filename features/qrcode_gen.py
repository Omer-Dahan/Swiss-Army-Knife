import io
import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

WAIT_TEXT = 1


async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📷 *יצירת קוד QR*\nשלח טקסט או קישור:", parse_mode="Markdown")
    return WAIT_TEXT


async def make_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await update.message.reply_photo(
        photo=buf,
        caption=f"✅ קוד QR עבור:\n`{text}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"(?i)^qr|^קוד qr$"), ask_text)],
        states={WAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, make_qr)]},
        fallbacks=[],
    )
    app.add_handler(conv)
