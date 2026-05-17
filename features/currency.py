import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

CHOOSE_DIR, WAIT_AMOUNT = range(2)


async def start_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    keyboard = [
        [
            InlineKeyboardButton("₪ שקל ← 💵 דולר", callback_data="cur_ils_usd"),
            InlineKeyboardButton("💵 דולר ← ₪ שקל", callback_data="cur_usd_ils"),
        ],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]
    await update.effective_message.reply_text(
        "💱 *המרת מטבע*\nבחר כיוון המרה:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSE_DIR


async def choose_direction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["cur_dir"] = query.data
    direction = "שקל → דולר" if query.data == "cur_ils_usd" else "דולר → שקל"
    await query.edit_message_text(f"כמה {direction} תרצה להמיר?")
    return WAIT_AMOUNT


async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ אנא שלח מספר תקין.")
        return WAIT_AMOUNT

    async with httpx.AsyncClient() as client:
        resp = await client.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        data = resp.json()

    usd_to_ils = data["rates"]["ILS"]

    if context.user_data.get("cur_dir") == "cur_ils_usd":
        result = amount / usd_to_ils
        text = f"₪{amount:,.2f} = 💵${result:,.4f}\n\n_שער: 1$ = ₪{usd_to_ils:.4f}_"
    else:
        result = amount * usd_to_ils
        text = f"💵${amount:,.2f} = ₪{result:,.2f}\n\n_שער: 1$ = ₪{usd_to_ils:.4f}_"

    keyboard = [
        [InlineKeyboardButton("🔄 המר עוד", callback_data="menu_currency")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^המרת מטבע$|^שקל דולר$|^דולר שקל$"), start_currency),
            CallbackQueryHandler(start_currency, pattern=r"^menu_currency$"),
        ],
        states={
            CHOOSE_DIR: [CallbackQueryHandler(choose_direction, pattern=r"^cur_")],
            WAIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, convert)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(conv)
