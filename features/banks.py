import httpx
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

BRANCH_API = (
    "https://data.gov.il/api/3/action/datastore_search"
    "?resource_id=360f1de2-76c7-4af3-b6e9-3a534bf4ef9d"
    "&filters={{\"bankCode\":\"{bank}\",\"branchCode\":\"{branch}\"}}&limit=1"
)


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
    msg = update.effective_message
    text = "🏦 <b>מספרי בנקים וסניפים</b>\nבחר בנק:"
    if update.callback_query:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=_bank_keyboard())
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=_bank_keyboard())
    return CHOOSE_BANK


async def choose_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    bank_code = query.data.replace("bank_", "")
    context.user_data["bank_code"] = bank_code
    bank_name = BANKS.get(bank_code, bank_code)
    keyboard = [
        [InlineKeyboardButton("🔙 חזרה לרשימת הבנקים", callback_data="menu_banks")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]
    await query.edit_message_text(
        f"בנק נבחר: <b>{bank_name}</b> (קוד {bank_code})\n\nשלח מספר סניף לחיפוש:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAIT_BRANCH


async def show_branch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    branch = update.message.text.strip().lstrip("0") or "0"
    bank_code = context.user_data.get("bank_code", "")
    bank_name = BANKS.get(bank_code, bank_code)

    keyboard = [
        [InlineKeyboardButton("🔄 חפש סניף נוסף", callback_data=f"bank_{bank_code}")],
        [InlineKeyboardButton("🔙 בחר בנק אחר", callback_data="menu_banks")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]

    try:
        url = (
            "https://data.gov.il/api/3/action/datastore_search"
            f"?resource_id=360f1de2-76c7-4af3-b6e9-3a534bf4ef9d"
            f"&filters={{\"bankCode\":\"{bank_code}\",\"branchCode\":\"{branch.zfill(3)}\"}}&limit=1"
        )
        async with httpx.AsyncClient() as client:
            data = (await client.get(url, timeout=10)).json()
        records = data.get("result", {}).get("records", [])
    except Exception:
        records = []

    if records:
        r = records[0]
        address = r.get("branchAddress", "")
        city = r.get("branchCity", "")
        phone = r.get("branchPhone", "")
        name = r.get("branchName", "")
        fax = r.get("branchFax", "")
        lines = [f"🏦 <b>{bank_name}</b> — סניף {branch}"]
        if name:
            lines.append(f"שם סניף: <b>{name}</b>")
        lines.append(f"קוד בנק: <code>{bank_code}</code> | קוד סניף: <code>{branch}</code>")
        if address or city:
            lines.append(f"כתובת: {address}{', ' + city if city else ''}")
        if phone:
            lines.append(f"טלפון: {phone}")
        if fax:
            lines.append(f"פקס: {fax}")
        text = "\n".join(lines)
    else:
        text = (
            f"🏦 <b>{bank_name}</b> — סניף {branch}\n"
            f"קוד בנק: <code>{bank_code}</code> | קוד סניף: <code>{branch}</code>\n\n"
            f"לא נמצאו פרטים עבור סניף זה. ייתכן שמספר הסניף שגוי."
        )

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^בנקים$|^מספרי בנק$|^סניף בנק$"), start_banks),
            CallbackQueryHandler(start_banks, pattern=r"^menu_banks$"),
            CallbackQueryHandler(choose_bank, pattern=r"^bank_"),
        ],
        states={
            CHOOSE_BANK: [CallbackQueryHandler(choose_bank, pattern=r"^bank_")],
            WAIT_BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, show_branch)],
        },
        per_message=False,
        fallbacks=[],
    )
    app.add_handler(conv)
