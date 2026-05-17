import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

WAIT_IP = 1


async def ask_ip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="cancel")]]
    await update.message.reply_text(
        "🌍 *מיקום לפי IP*\nשלח כתובת IP (או השאר ריק לבדיקת ה-IP שלך):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAIT_IP


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ip = update.message.text.strip()
    url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
    async with httpx.AsyncClient() as client:
        data = (await client.get(url)).json()

    if data.get("status") != "success":
        await update.message.reply_text("❌ לא הצלחתי לאתר את ה-IP הזה.")
        return ConversationHandler.END

    text = (
        f"🌍 *מיקום משוער ל-{data.get('query')}*\n"
        f"מדינה: {data.get('country')}\n"
        f"עיר: {data.get('city')}\n"
        f"ISP: {data.get('isp')}\n"
        f"אזור זמן: {data.get('timezone')}"
    )
    maps_url = f"https://maps.google.com/?q={data['lat']},{data['lon']}"
    keyboard = [
        [InlineKeyboardButton("🗺️ פתח במפות", url=maps_url)],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"(?i)^מיקום ip$|^ip location$"), ask_ip)],
        states={WAIT_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)]},
        fallbacks=[],
    )
    app.add_handler(conv)
