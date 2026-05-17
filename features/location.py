import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

WAIT_IP = 1


async def ask_ip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await update.effective_message.reply_text(
        "🌍 *מיקום לפי IP*\nשלח כתובת IP (לדוגמה: 8.8.8.8):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAIT_IP


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    # strip http(s):// prefix if user pasted a URL with an IP
    import re
    url_ip = re.match(r"^https?://(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:[:/].*)?$", raw, re.I)
    ip = url_ip.group(1) if url_ip else raw

    keyboard = [
        [InlineKeyboardButton("🔄 בדוק IP נוסף", callback_data="menu_ip")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]

    try:
        url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
        async with httpx.AsyncClient() as client:
            data = (await client.get(url, timeout=10)).json()
    except Exception:
        await update.message.reply_text(
            "❌ שגיאה בחיבור לשירות המיקום.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return ConversationHandler.END

    if data.get("status") != "success":
        await update.message.reply_text(
            "❌ לא הצלחתי לאתר את ה-IP הזה.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return ConversationHandler.END

    text = (
        f"🌍 *מיקום משוער ל-{data.get('query')}*\n"
        f"מדינה: {data.get('country')} ({data.get('countryCode')})\n"
        f"אזור: {data.get('regionName', '')}\n"
        f"עיר: {data.get('city')}\n"
        f"ISP: {data.get('isp')}\n"
        f"ארגון: {data.get('org', '')}\n"
        f"אזור זמן: {data.get('timezone')}"
    )
    maps_url = f"https://maps.google.com/?q={data['lat']},{data['lon']}"
    keyboard_with_map = [
        [InlineKeyboardButton("🗺️ פתח במפות", url=maps_url)],
        [InlineKeyboardButton("🔄 בדוק IP נוסף", callback_data="menu_ip")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard_with_map)
    )
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^מיקום ip$|^ip location$"), ask_ip),
            CallbackQueryHandler(ask_ip, pattern=r"^menu_ip$"),
        ],
        states={WAIT_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)]},
        fallbacks=[],
    )
    app.add_handler(conv)
