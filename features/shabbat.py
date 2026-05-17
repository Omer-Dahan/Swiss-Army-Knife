import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

CHOOSE_CITY = 1

CITIES = {
    "ירושלים": "281184",
    "תל אביב": "293397",
    "חיפה": "294801",
    "באר שבע": "294777",
    "אשדוד": "295629",
    "נתניה": "293690",
    "פתח תקווה": "293408",
    "רמת גן": "293248",
    "ראשון לציון": "293222",
    "הרצליה": "294778",
}


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    rows = [
        [InlineKeyboardButton(city, callback_data=f"shab_{geoname}")]
        for city, geoname in list(CITIES.items())[:5]
    ] + [
        [InlineKeyboardButton(city, callback_data=f"shab_{geoname}")]
        for city, geoname in list(CITIES.items())[5:]
    ] + [
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    await update.effective_message.reply_text(
        "🕯️ *זמני שבת*\nבחר עיר:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return CHOOSE_CITY


async def show_times(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    geoname_id = query.data.replace("shab_", "")
    city_name = next((c for c, g in CITIES.items() if g == geoname_id), geoname_id)

    url = (
        f"https://www.hebcal.com/shabbat?cfg=json&geonameid={geoname_id}"
        f"&m=50&b=18&M=on"
    )
    async with httpx.AsyncClient() as client:
        data = (await client.get(url, timeout=10)).json()

    items = {item["category"]: item for item in data.get("items", [])}
    candles = items.get("candles", {})
    havdalah = items.get("havdalah", {})

    def fmt(iso: str) -> str:
        try:
            dt = datetime.fromisoformat(iso)
            return dt.strftime("%H:%M")
        except Exception:
            return iso

    parasha = items.get("parashat", {}).get("title", "")
    text = (
        f"🕯️ *זמני שבת — {city_name}*\n"
        f"פרשת השבוע: {parasha}\n\n"
        f"כניסת שבת: *{fmt(candles.get('date', ''))}*\n"
        f"יציאת שבת: *{fmt(havdalah.get('date', ''))}*"
    )
    keyboard = [
        [InlineKeyboardButton("🔙 חזרה לבחירת עיר", callback_data="menu_shabbat")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^זמני שבת$|^שבת$"), ask_city),
            CallbackQueryHandler(ask_city, pattern=r"^menu_shabbat$"),
        ],
        states={CHOOSE_CITY: [CallbackQueryHandler(show_times, pattern=r"^shab_")]},
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(conv)
