import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

WAIT_PASSWORD = 1


def _analyze(pw: str) -> dict:
    score = 0
    tips = []

    length = len(pw)
    if length >= 16:
        score += 3
    elif length >= 12:
        score += 2
    elif length >= 8:
        score += 1
    else:
        tips.append("הוסף תווים — מינימום 8, עדיף 12+")

    has_upper = bool(re.search(r"[A-Z]", pw))
    has_lower = bool(re.search(r"[a-z]", pw))
    has_digit = bool(re.search(r"\d", pw))
    has_symbol = bool(re.search(r"[^A-Za-z0-9]", pw))

    if has_upper: score += 1
    else: tips.append("הוסף אותיות גדולות (A-Z)")
    if has_lower: score += 1
    else: tips.append("הוסף אותיות קטנות (a-z)")
    if has_digit: score += 1
    else: tips.append("הוסף ספרות (0-9)")
    if has_symbol: score += 2
    else: tips.append("הוסף סמלים (!@#$%...)")

    # common patterns penalty
    if re.search(r"(012|123|234|345|456|567|678|789|890|abc|qwerty|password|admin|1111|aaaa)", pw.lower()):
        score -= 2
        tips.append("הימנע מרצפים צפויים (123, qwerty...)")

    score = max(0, min(score, 8))
    levels = [
        (2,  "💀 חלשה מאוד",  "🔴"),
        (4,  "😟 חלשה",        "🟠"),
        (5,  "😐 בינונית",     "🟡"),
        (6,  "🙂 טובה",        "🟢"),
        (8,  "💪 חזקה מאוד",   "🟢"),
    ]
    label, emoji = "💀 חלשה מאוד", "🔴"
    for threshold, lbl, emj in levels:
        if score >= threshold:
            label, emoji = lbl, emj

    bar_filled = round(score / 8 * 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    return {"score": score, "label": label, "emoji": emoji, "bar": bar, "tips": tips}


async def ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        "🔍 *בדיקת חוזק סיסמא*\nשלח סיסמא לבדיקה:",
        parse_mode="Markdown",
    )
    return WAIT_PASSWORD


async def check_strength(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pw = update.message.text.strip()
    r = _analyze(pw)

    tips_text = "\n".join(f"• {t}" for t in r["tips"]) if r["tips"] else "• אין הערות — סיסמא מצוינת!"

    keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await update.message.reply_text(
        f"🔐 *ניתוח סיסמא*\n\n"
        f"{r['emoji']} *{r['label']}*\n"
        f"`{r['bar']}` {r['score']}/8\n\n"
        f"📋 *המלצות:*\n{tips_text}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"(?i)^חוזק סיסמ|^בדיקת סיסמ|^בדוק סיסמ"), ask_password),
            CallbackQueryHandler(ask_password, pattern=r"^menu_pwcheck$"),
        ],
        states={WAIT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_strength)]},
        fallbacks=[],
    )
    app.add_handler(conv)
