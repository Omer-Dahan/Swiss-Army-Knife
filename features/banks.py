from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

CHOOSE_BANK, WAIT_BRANCH = range(2)

BANKS = {
    "10": "בנק לאומי",
    "11": "בנק דיסקונט",
    "12": "בנק הפועלים",
    "13": "בנק אגוד",
    "14": "בנק אוצר החייל",
    "17": "בנק מרכנתיל דיסקונט",
    "20": "בנק מזרחי טפחות",
    "22": "בנק CitiBank",
    "23": "HSBC",
    "26": "יובנק",
    "31": "בנק הבינלאומי",
    "34": "בנק ערבי ישראלי",
    "46": "בנק מסד",
    "52": "בנק פועלי אגודת ישראל",
    "54": "בנק ירושלים",
    "58": "בנק ויזה כ.א.ל",
    "65": "בנק אל מגרב",
    "68": "בנק דקסיה ישראל",
    "99": "בנק הדואר",
}


def _bank_keyboard() -> InlineKeyboardMarkup:
    rows = []
    items = list(BANKS.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(f"{v} ({k})", callback_data=f"bank_{k}") for k, v in items[i:i+2]]
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")])
    return InlineKeyboardMarkup(rows)


async def start_banks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        "🏦 <b>מספרי בנקים וסניפים</b>\nבחר בנק:",
        parse_mode="HTML",
        reply_markup=_bank_keyboard(),
    )
    return CHOOSE_BANK


async def choose_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    bank_code = query.data.replace("bank_", "")
    context.user_data["bank_code"] = bank_code
    bank_name = BANKS.get(bank_code, bank_code)
    keyboard = [[InlineKeyboardButton("🔙 חזרה לרשימת הבנקים", callback_data="menu_banks")],
                [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await query.edit_message_text(
        f"בנק נבחר: <b>{bank_name}</b> (קוד {bank_code})\n\nשלח מספר סניף לחיפוש (או שלח * לראות פרטי בנק):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAIT_BRANCH


async def show_branch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    branch = update.message.text.strip()
    bank_code = context.user_data.get("bank_code", "")
    bank_name = BANKS.get(bank_code, bank_code)

    if branch == "*":
        keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
        await update.message.reply_text(
            f"🏦 <b>{bank_name}</b>\nקוד בנק: <code>{bank_code}</code>\n\nלחיפוש סניף ספציפי, שלח את מספרו.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WAIT_BRANCH

    await update.message.reply_text(
        f"🏦 <b>{bank_name}</b> — סניף {branch}\n"
        f"קוד בנק: <code>{bank_code}</code> | קוד סניף: <code>{branch}</code>\n\n"
        f"לבירור פרטי הסניף המלאים (כתובת, טלפון) פנה לאתר הבנק או לשירות הלקוחות.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^בנקים$|^מספרי בנק$|^סניף בנק$"), start_banks),
            CallbackQueryHandler(start_banks, pattern=r"^menu_banks$"),
        ],
        states={
            CHOOSE_BANK: [CallbackQueryHandler(choose_bank, pattern=r"^bank_")],
            WAIT_BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, show_branch)],
        },
        per_message=False,
        fallbacks=[],
    )
    app.add_handler(conv)
