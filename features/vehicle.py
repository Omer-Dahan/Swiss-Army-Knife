import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

WAIT_PLATE = 1


async def ask_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        "🚗 *חיפוש רכב*\nשלח מספר רישוי (לדוגמה: 12-345-67):",
        parse_mode="Markdown",
    )
    return WAIT_PLATE


async def search_vehicle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    plate = update.message.text.strip().replace("-", "").replace(" ", "")
    url = (
        "https://data.gov.il/api/3/action/datastore_search"
        f"?resource_id=053cea08-09bc-40ec-8f7a-156f0677aff3&q={plate}&limit=1"
    )
    try:
        async with httpx.AsyncClient() as client:
            data = (await client.get(url, timeout=15)).json()
        records = data.get("result", {}).get("records", [])
    except Exception:
        await update.message.reply_text("❌ שגיאה בחיבור למאגר הממשלתי.")
        return ConversationHandler.END

    if not records:
        await update.message.reply_text(f"❌ לא נמצאו תוצאות למספר רישוי {plate}.")
        return ConversationHandler.END

    r = records[0]
    fields = {
        "יצרן": r.get("tozeret_nm", ""),
        "דגם": r.get("kinuy_mishari", ""),
        "שנת ייצור": r.get("shnat_yitzur", ""),
        "צבע": r.get("tzeva_rechev", ""),
        "סוג דלק": r.get("sug_delek_nm", ""),
        "בעלות": r.get("baalut", ""),
        "תוקף טסט": r.get("tokef_dt", ""),
        "מספר כיסאות": r.get("mispar_moshavim", ""),
        "נפח מנוע": r.get("nefah_manoa", ""),
        "קילומטראז": r.get("km_acharon_b", ""),
    }
    lines = "\n".join(f"• {k}: *{v}*" for k, v in fields.items() if v)
    await update.message.reply_text(
        f"🚗 *רכב {plate}*\n\n{lines}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^רכב$|^חיפוש רכב$|^מספר רישוי$"), ask_plate),
            CallbackQueryHandler(ask_plate, pattern=r"^menu_vehicle$"),
        ],
        states={WAIT_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_vehicle)]},
        fallbacks=[],
    )
    app.add_handler(conv)
