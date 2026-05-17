import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, TypeHandler

from features import (
    whatsapp,
    location,
    shorturl,
    qrcode_gen,
    image_pdf,
    password_gen,
    password_strength,
    currency,
    shabbat,
    banks,
    vehicle,
    vat,
    hebrew_fix,
    dice,
    world_clock,
    notes,
    smart,
    image_icon,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")


async def reset_state_interceptor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query and update.callback_query.data:
        data = update.callback_query.data
        if data.startswith("menu_") or data == "go_home":
            from telegram.ext import ConversationHandler
            try:
                for group in context.application.handlers.values():
                    for handler in group:
                        if isinstance(handler, ConversationHandler):
                            chat_id = update.effective_chat.id if update.effective_chat else None
                            user_id = update.effective_user.id if update.effective_user else None
                            if chat_id and user_id:
                                key = (chat_id, user_id)
                                if hasattr(handler, "_conversations") and key in handler._conversations:
                                    del handler._conversations[key]
            except Exception:
                pass


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        # תקשורת
        [InlineKeyboardButton("📲 קישור ישיר לוואטסאפ", callback_data="menu_wa")],
        # כלי רשת
        [
            InlineKeyboardButton("🌍 מיקום לפי IP",  callback_data="menu_ip"),
            InlineKeyboardButton("🔗 קיצור URL",      callback_data="menu_short"),
        ],
        # יצירה
        [
            InlineKeyboardButton("📷 קוד QR",          callback_data="menu_qr"),
            InlineKeyboardButton("📄 תמונה ↔ PDF",     callback_data="menu_pdf"),
        ],
        [
            InlineKeyboardButton("🖼️ תמונה לאייקון",   callback_data="menu_icon"),
        ],
        # כספים
        [
            InlineKeyboardButton("💱 המרת מטבע",       callback_data="menu_currency"),
            InlineKeyboardButton("🧾 מחשבון מע\"מ",    callback_data="menu_vat"),
        ],
        # ישראל
        [
            InlineKeyboardButton("🕯️ זמני שבת",        callback_data="menu_shabbat"),
            InlineKeyboardButton("🏦 בנקים וסניפים",   callback_data="menu_banks"),
        ],
        [
            InlineKeyboardButton("🚗 חיפוש רכב",       callback_data="menu_vehicle"),
            InlineKeyboardButton("🌍 שעון עולמי",      callback_data="menu_clock"),
        ],
        # סיסמאות
        [
            InlineKeyboardButton("🔐 מגנרט סיסמאות", callback_data="menu_pw"),
            InlineKeyboardButton("🔍 חוזק סיסמא",      callback_data="menu_pwcheck"),
        ],
        # כלים נוספים
        [
            InlineKeyboardButton("⌨️ תיקון מקלדת",     callback_data="menu_hebfix"),
            InlineKeyboardButton("🎲 זריקת קוביות",    callback_data="menu_dice"),
        ],
        # הערות
        [InlineKeyboardButton("📓 ההערות שלי",          callback_data="menu_notes")],
    ])


_SIMPLE_INSTRUCTIONS = {
    "menu_wa":    "שלח מספר טלפון:",
    "menu_short": "שלח קישור לקיצור:",
    "menu_qr":    "שלח טקסט או קישור לקוד QR:",
    "menu_pdf":   "📄 שלח תמונה (JPG/PNG) לקבלת PDF, או שלח קובץ PDF לקבלת תמונה.",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ברוך הבא לאולר השוויצרי! 🇨🇭\n"
        "בחר כלי מהתפריט, או שלח ישירות:\n"
        "• כתובת IP לזיהוי מיקום\n"
        "• מספר רישוי לחיפוש רכב\n"
        "• קישור לקיצור / QR\n"
        "• מספר טלפון לוואטסאפ\n"
        "• סכום למחשבון מע\"מ / המרת מטבע",
        reply_markup=main_menu(),
    )


_HOME_TEXT = (
    "ברוך הבא לאולר השוויצרי! 🇨🇭\n"
    "בחר כלי מהתפריט, או שלח ישירות:\n"
    "• כתובת IP לזיהוי מיקום\n"
    "• מספר רישוי לחיפוש רכב\n"
    "• קישור לקיצור / QR\n"
    "• מספר טלפון לוואטסאפ\n"
    "• סכום למחשבון מע\"מ / המרת מטבע"
)


async def go_home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("smart_amount", None)
    context.user_data.pop("smart_text", None)

    # Try to edit the existing message in-place.
    # This fails if the message contains media (photo/document) — in that case
    # we fall back to editing the caption, and if that also fails, send a new message.
    from telegram.error import BadRequest
    try:
        await query.edit_message_text(_HOME_TEXT, reply_markup=main_menu())
    except BadRequest:
        try:
            await query.edit_message_caption(caption=_HOME_TEXT, reply_markup=main_menu())
        except BadRequest:
            await query.message.reply_text(_HOME_TEXT, reply_markup=main_menu())


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    msg = _SIMPLE_INSTRUCTIONS.get(query.data, "")
    if msg:
        keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN חסר ב-.env")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(TypeHandler(Update, reset_state_interceptor), group=-1)
    app.add_handler(CallbackQueryHandler(go_home_callback, pattern=r"^go_home$"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu_(wa|short|qr|pdf)$"))

    # ConversationHandlers ראשונים — חייבים להיות לפני menu_callback הכללי
    location.register(app)
    shorturl.register(app)
    qrcode_gen.register(app)
    password_gen.register(app)
    password_strength.register(app)
    currency.register(app)
    shabbat.register(app)
    banks.register(app)
    vehicle.register(app)
    vat.register(app)
    hebrew_fix.register(app)
    dice.register(app)
    notes.register(app)
    image_icon.register(app)

    # handlers שאינם conversation
    world_clock.register(app)
    whatsapp.register(app)
    image_pdf.register(app)

    # מצב חכם אחרון — תופס כל שאר הטקסט
    smart.register(app)

    print("הבוט פועל...")
    app.run_polling()


if __name__ == "__main__":
    main()
