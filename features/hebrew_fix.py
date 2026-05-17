from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

WAIT_TEXT = 1

# מיפוי מקלדת אנגלית → עברית (QWERTY ↔ עברית)
_EN_TO_HE = {
    'q': '/', 'w': "'", 'e': 'ק', 'r': 'ר', 't': 'א', 'y': 'ט',
    'u': 'ו', 'i': 'ן', 'o': 'ם', 'p': 'פ', '[': ']', ']': '[',
    'a': 'ש', 's': 'ד', 'd': 'ג', 'f': 'כ', 'g': 'ע', 'h': 'י',
    'j': 'ח', 'k': 'ל', 'l': 'ך', ';': 'ף', "'": ',',
    'z': 'ז', 'x': 'ס', 'c': 'ב', 'v': 'ה', 'b': 'נ', 'n': 'מ',
    'm': 'צ', ',': 'ת', '.': 'ץ', '/': '.',
    'Q': '/', 'W': "'", 'E': 'ק', 'R': 'ר', 'T': 'א', 'Y': 'ט',
    'U': 'ו', 'I': 'ן', 'O': 'ם', 'P': 'פ',
    'A': 'ש', 'S': 'ד', 'D': 'ג', 'F': 'כ', 'G': 'ע', 'H': 'י',
    'J': 'ח', 'K': 'ל', 'L': 'ך',
    'Z': 'ז', 'X': 'ס', 'C': 'ב', 'V': 'ה', 'B': 'נ', 'N': 'מ',
    'M': 'צ',
}


def fix_hebrew(text: str) -> str:
    return "".join(_EN_TO_HE.get(ch, ch) for ch in text)


async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        "⌨️ *תיקון מקלדת עברית/אנגלית*\n"
        "שלח את הטקסט שהקלדת בפריסה הלא נכונה:",
        parse_mode="Markdown",
    )
    return WAIT_TEXT


async def do_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    original = update.message.text.strip()
    fixed = fix_hebrew(original)
    keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await update.message.reply_text(
        f"🔤 *מקורי:*\n`{original}`\n\n"
        f"✅ *מתוקן:*\n`{fixed}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^תיקון מקלדת$|^תקן טקסט$|^עברית אנגלית$"), ask_text),
            CallbackQueryHandler(ask_text, pattern=r"^menu_hebfix$"),
        ],
        states={WAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_fix)]},
        fallbacks=[],
    )
    app.add_handler(conv)
