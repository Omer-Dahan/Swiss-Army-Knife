"""
Smart mode: detects user intent from free text and routes to the right feature.
Registered LAST so it catches only messages not handled by other features.
"""
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler

# ── patterns ────────────────────────────────────────────────────────────────
_PLATE_RE = re.compile(r"^\d{5,8}$|^\d{2,3}-\d{3}-\d{2,3}$")
_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_URL_IP_RE = re.compile(r"^https?://(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:[:/].*)?$", re.I)
_PHONE_RE = re.compile(r"^[\d\s\+\-\(\)]{7,15}$")
_AMOUNT_RE = re.compile(r"^[\d\.,]+$")


async def smart_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    # URL with bare IP → IP lookup
    url_ip_match = _URL_IP_RE.match(text)
    if url_ip_match:
        update.message.text = url_ip_match.group(1)
        from features.location import get_location
        await get_location(update, context)
        return

    # bare IP address → IP lookup
    if _IP_RE.match(text):
        from features.location import get_location
        await get_location(update, context)
        return

    # license plate (Israeli format)
    if _PLATE_RE.match(text.replace("-", "").replace(" ", "")):
        from features.vehicle import search_vehicle
        await search_vehicle(update, context)
        return

    # URL → suggest QR or shorten
    if _URL_RE.search(text):
        keyboard = [
            [
                InlineKeyboardButton("📷 צור קוד QR", callback_data="smart_qr"),
                InlineKeyboardButton("🔗 קצר קישור", callback_data="smart_short"),
            ]
        ]
        context.user_data["smart_text"] = text
        await update.message.reply_text(
            "🔍 זיהיתי קישור — מה תרצה לעשות?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # phone number → WhatsApp
    if _PHONE_RE.match(text):
        from features.whatsapp import handle_number
        await handle_number(update, context)
        return

    # plain number → VAT or currency?
    if _AMOUNT_RE.match(text):
        keyboard = [
            [
                InlineKeyboardButton("🧾 מחשבון מע\"מ", callback_data="smart_vat"),
                InlineKeyboardButton("💱 המרת מטבע", callback_data="smart_currency"),
            ]
        ]
        context.user_data["smart_amount"] = text
        await update.message.reply_text(
            f"🔍 זיהיתי סכום *{text}* — מה תרצה לעשות?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return


async def smart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "smart_qr":
        import io, qrcode
        text = context.user_data.get("smart_text", "")
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await query.message.reply_photo(photo=buf, caption=f"✅ קוד QR:\n`{text}`", parse_mode="Markdown")

    elif action == "smart_short":
        import httpx
        url = context.user_data.get("smart_text", "")
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://tinyurl.com/api-create.php?url={url}", timeout=10)
        short = resp.text.strip()
        keyboard = [[InlineKeyboardButton("🔗 פתח", url=short)]]
        await query.message.reply_text(f"✅ `{short}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == "smart_vat":
        from features.vat import start_vat, VAT_RATE
        keyboard = [
            [
                InlineKeyboardButton("➕ הוסף מע\"מ למחיר", callback_data="vat_add"),
                InlineKeyboardButton("➖ הפחת מע\"מ ממחיר", callback_data="vat_remove"),
            ],
            [InlineKeyboardButton("📊 כמה מע\"מ כלול?", callback_data="vat_how_much")],
            [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
        ]
        await query.message.reply_text(
            f"🧾 *מחשבון מע\"מ* ({int(VAT_RATE*100)}%) — סכום: *{context.user_data.get('smart_amount')}*\nבחר פעולה:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif action == "smart_currency":
        keyboard = [
            [
                InlineKeyboardButton("₪ שקל → 💵 דולר", callback_data="cur_ils_usd"),
                InlineKeyboardButton("💵 דולר → ₪ שקל", callback_data="cur_usd_ils"),
            ],
            [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
        ]
        await query.message.reply_text(
            f"💱 *המרת מטבע* — סכום: *{context.user_data.get('smart_amount')}*\nבחר כיוון המרה:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(smart_callback, pattern=r"^smart_"))
    # Fallback: catch ALL remaining text — must be registered last in bot.py
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, smart_dispatch))
