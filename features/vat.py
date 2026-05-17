from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

CHOOSE_MODE, WAIT_AMOUNT = range(2)

VAT_RATE = 0.18


async def start_vat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    keyboard = [
        [
            InlineKeyboardButton("➕ הוסף מע\"מ למחיר", callback_data="vat_add"),
            InlineKeyboardButton("➖ הפחת מע\"מ ממחיר", callback_data="vat_remove"),
        ],
        [InlineKeyboardButton("📊 כמה מע\"מ כלול?", callback_data="vat_how_much")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]
    await update.effective_message.reply_text(
        f"🧾 *מחשבון מע\"מ* ({int(VAT_RATE*100)}%)\nבחר פעולה:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSE_MODE


async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["vat_mode"] = query.data
    prompts = {
        "vat_add": "שלח מחיר לפני מע\"מ (ללא מע\"מ):",
        "vat_remove": "שלח מחיר כולל מע\"מ:",
        "vat_how_much": "שלח מחיר כולל מע\"מ:",
    }
    await query.edit_message_text(prompts[query.data])
    return WAIT_AMOUNT


async def calc_vat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip().replace(",", "."))
        assert amount > 0
    except (ValueError, AssertionError):
        await update.message.reply_text("❌ אנא שלח סכום חיובי.")
        return WAIT_AMOUNT

    mode = context.user_data.get("vat_mode", "vat_add")

    if mode == "vat_add":
        vat = amount * VAT_RATE
        total = amount + vat
        text = (
            f"🧾 *הוספת מע\"מ*\n"
            f"מחיר לפני מע\"מ: ₪{amount:,.2f}\n"
            f"מע\"מ ({int(VAT_RATE*100)}%): ₪{vat:,.2f}\n"
            f"━━━━━━━━━━━\n"
            f"*סה\"כ כולל מע\"מ: ₪{total:,.2f}*"
        )
    elif mode == "vat_remove":
        before = amount / (1 + VAT_RATE)
        vat = amount - before
        text = (
            f"🧾 *הפחתת מע\"מ*\n"
            f"מחיר כולל מע\"מ: ₪{amount:,.2f}\n"
            f"מע\"מ ({int(VAT_RATE*100)}%): ₪{vat:,.2f}\n"
            f"━━━━━━━━━━━\n"
            f"*מחיר לפני מע\"מ: ₪{before:,.2f}*"
        )
    else:
        vat = amount - (amount / (1 + VAT_RATE))
        text = (
            f"🧾 *מע\"מ הכלול*\n"
            f"מחיר כולל מע\"מ: ₪{amount:,.2f}\n"
            f"━━━━━━━━━━━\n"
            f"*מע\"מ הכלול: ₪{vat:,.2f}*"
        )

    keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'(?i)^מע"מ$|^מחשבון מע"מ$|^מעמ$'), start_vat),
            CallbackQueryHandler(start_vat, pattern=r"^menu_vat$"),
        ],
        states={
            CHOOSE_MODE: [CallbackQueryHandler(choose_mode, pattern=r"^vat_")],
            WAIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, calc_vat)],
        },
        per_message=False,
        fallbacks=[],
    )
    app.add_handler(conv)
