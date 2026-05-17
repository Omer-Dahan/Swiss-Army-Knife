from datetime import datetime
import zoneinfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler

CITIES = [
    ("🇮🇱 ירושלים",    "Asia/Jerusalem"),
    ("🇬🇧 לונדון",      "Europe/London"),
    ("🇫🇷 פריז",        "Europe/Paris"),
    ("🇩🇪 ברלין",       "Europe/Berlin"),
    ("🇷🇺 מוסקבה",      "Europe/Moscow"),
    ("🇦🇪 דובאי",       "Asia/Dubai"),
    ("🇮🇳 מומבאי",      "Asia/Kolkata"),
    ("🇨🇳 בייג'ינג",    "Asia/Shanghai"),
    ("🇯🇵 טוקיו",       "Asia/Tokyo"),
    ("🇦🇺 סידני",       "Australia/Sydney"),
    ("🇧🇷 סאו פאולו",   "America/Sao_Paulo"),
    ("🇺🇸 ניו יורק",    "America/New_York"),
    ("🇺🇸 שיקגו",       "America/Chicago"),
    ("🇺🇸 לוס אנג'לס", "America/Los_Angeles"),
]


def _clock_text() -> str:
    now_utc = datetime.now(tz=zoneinfo.ZoneInfo("UTC"))
    lines = []
    for name, tz in CITIES:
        local = now_utc.astimezone(zoneinfo.ZoneInfo(tz))
        lines.append(f"{name:<18} `{local.strftime('%H:%M')}` _{local.strftime('%d/%m')}_")
    return "🌍 *שעון עולמי*\n\n" + "\n".join(lines)


async def show_clock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("🔄 רענן", callback_data="clock_refresh")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    await update.effective_message.reply_text(
        _clock_text(),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def refresh_clock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🔄 רענן", callback_data="clock_refresh")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    await query.edit_message_text(
        _clock_text(),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


def register(app) -> None:
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^שעון עולמי$|^זמן בעולם$|^שעה בעולם$"), show_clock))
    app.add_handler(CallbackQueryHandler(show_clock, pattern=r"^menu_clock$"))
    app.add_handler(CallbackQueryHandler(refresh_clock, pattern=r"^clock_refresh$"))
