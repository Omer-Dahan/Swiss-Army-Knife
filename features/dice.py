import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

CHOOSE_DICE, WAIT_COUNT = range(2)

DICE_TYPES = {
    "d4": 4, "d6": 6, "d8": 8,
    "d10": 10, "d12": 12, "d20": 20, "d100": 100,
}

DICE_EMOJI = {
    4: "🔺", 6: "🎲", 8: "🔷",
    10: "🔟", 12: "🔵", 20: "🌟", 100: "💯",
}


async def ask_dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    keyboard = [
        [
            InlineKeyboardButton("🔺 D4",  callback_data="dice_d4"),
            InlineKeyboardButton("🎲 D6",  callback_data="dice_d6"),
            InlineKeyboardButton("🔷 D8",  callback_data="dice_d8"),
        ],
        [
            InlineKeyboardButton("🔟 D10", callback_data="dice_d10"),
            InlineKeyboardButton("🔵 D12", callback_data="dice_d12"),
            InlineKeyboardButton("🌟 D20", callback_data="dice_d20"),
        ],
        [InlineKeyboardButton("💯 D100 (אחוזים)", callback_data="dice_d100")],
    ]
    await update.effective_message.reply_text(
        "🎲 *הדמיית זריקת קוביות*\nבחר סוג קובייה:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSE_DICE


async def choose_dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    die = query.data.replace("dice_", "")
    context.user_data["dice_type"] = die
    await query.edit_message_text(
        f"כמה קוביות {die.upper()} לזרוק? (1–20):",
        parse_mode="Markdown",
    )
    return WAIT_COUNT


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        count = int(update.message.text.strip())
        assert 1 <= count <= 20
    except (ValueError, AssertionError):
        await update.message.reply_text("❌ שלח מספר בין 1 ל-20.")
        return WAIT_COUNT

    die = context.user_data.get("dice_type", "d6")
    sides = DICE_TYPES.get(die, 6)
    emoji = DICE_EMOJI.get(sides, "🎲")
    results = [random.randint(1, sides) for _ in range(count)]
    total = sum(results)

    rolls_str = "  ".join(f"`{r}`" for r in results)
    text = (
        f"{emoji} *{count}×{die.upper()}*\n\n"
        f"תוצאות: {rolls_str}\n"
        f"━━━━━━━━━━━\n"
        f"*סה\"כ: {total}*"
    )
    keyboard = [
        [InlineKeyboardButton("🔄 זרוק שוב", callback_data=f"reroll_{die}_{count}")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


async def reroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, die, count_str = query.data.split("_")
    count = int(count_str)
    sides = DICE_TYPES.get(die, 6)
    emoji = DICE_EMOJI.get(sides, "🎲")
    results = [random.randint(1, sides) for _ in range(count)]
    total = sum(results)
    rolls_str = "  ".join(f"`{r}`" for r in results)
    text = (
        f"{emoji} *{count}×{die.upper()}*\n\n"
        f"תוצאות: {rolls_str}\n"
        f"━━━━━━━━━━━\n"
        f"*סה\"כ: {total}*"
    )
    keyboard = [
        [InlineKeyboardButton("🔄 זרוק שוב", callback_data=f"reroll_{die}_{count}")],
        [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


def register(app) -> None:
    from telegram.ext import CallbackQueryHandler
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^קוביה$|^קוביות$|^זריקת קובי"), ask_dice),
            CallbackQueryHandler(ask_dice, pattern=r"^menu_dice$"),
        ],
        states={
            CHOOSE_DICE: [CallbackQueryHandler(choose_dice, pattern=r"^dice_")],
            WAIT_COUNT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, roll)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(reroll, pattern=r"^reroll_"))
