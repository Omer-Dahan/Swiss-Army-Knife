import html
import secrets
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

CHOOSE_OPTIONS, WAIT_LENGTH = range(2)

_CHARSET_KEYS = {
    "upper": string.ascii_uppercase,
    "lower": string.ascii_lowercase,
    "digits": string.digits,
    "symbols": "!@#$%^&*()-_=+[]{}|;:,.<>?",
}


def _build_keyboard(selected: set) -> InlineKeyboardMarkup:
    labels = {"upper": "ABC אותיות גדולות", "lower": "abc אותיות קטנות", "digits": "123 ספרות", "symbols": "!@# סמלים"}
    rows = [
        [InlineKeyboardButton(("✅ " if k in selected else "☐ ") + v, callback_data=f"pw_{k}")]
        for k, v in labels.items()
    ]
    rows.append([InlineKeyboardButton("✔️ המשך", callback_data="pw_done")])
    return InlineKeyboardMarkup(rows)


async def start_pw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data["pw_selected"] = {"upper", "lower", "digits"}
    await update.effective_message.reply_text(
        "🔐 *מגנרטור סיסמאות*\nבחר סוגי תווים:",
        parse_mode="Markdown",
        reply_markup=_build_keyboard(context.user_data["pw_selected"]),
    )
    return CHOOSE_OPTIONS


async def toggle_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    key = query.data.replace("pw_", "")
    selected = context.user_data.setdefault("pw_selected", set())
    if key in selected:
        selected.discard(key)
    else:
        selected.add(key)
    await query.edit_message_reply_markup(_build_keyboard(selected))
    return CHOOSE_OPTIONS


async def ask_length(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("pw_selected"):
        await query.answer("בחר לפחות סוג תווים אחד!", show_alert=True)
        return CHOOSE_OPTIONS
    await query.edit_message_text("כמה תווים תרצה? (4–128):", parse_mode="Markdown")
    return WAIT_LENGTH


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        length = int(update.message.text.strip())
        assert 4 <= length <= 128
    except (ValueError, AssertionError):
        await update.message.reply_text("❌ אנא שלח מספר בין 4 ל-128.")
        return WAIT_LENGTH

    context.user_data["pw_length"] = length
    charset = "".join(_CHARSET_KEYS[k] for k in context.user_data.get("pw_selected", _CHARSET_KEYS))
    password = "".join(secrets.choice(charset) for _ in range(length))
    keyboard = [
        [InlineKeyboardButton("🔄 צור שוב", callback_data="pw_regen")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    await update.message.reply_text(
        f"✅ הסיסמה שלך:\n<code>{html.escape(password)}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


async def regen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    charset = "".join(_CHARSET_KEYS[k] for k in context.user_data.get("pw_selected", _CHARSET_KEYS))
    length = context.user_data.get("pw_length", 16)
    password = "".join(secrets.choice(charset) for _ in range(length))
    keyboard = [
        [InlineKeyboardButton("🔄 צור שוב", callback_data="pw_regen")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    await query.edit_message_text(
        f"✅ הסיסמה שלך:\n<code>{html.escape(password)}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^סיסמה|^מגנרטור סיסמ"), start_pw),
            CallbackQueryHandler(start_pw, pattern=r"^menu_pw$"),
        ],
        states={
            CHOOSE_OPTIONS: [
                CallbackQueryHandler(toggle_option, pattern=r"^pw_(upper|lower|digits|symbols)$"),
                CallbackQueryHandler(ask_length, pattern=r"^pw_done$"),
            ],
            WAIT_LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)],
        },
        per_message=False,
        fallbacks=[],
    )
    app.add_handler(conv)
