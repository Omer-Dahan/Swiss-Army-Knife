"""
Notes are stored per-user in a JSON file: data/notes_{user_id}.json
Each note: {"id": int, "text": str, "created": str}
"""
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, filters,
)

NOTES_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ADD_NOTE, EDIT_CHOOSE, EDIT_TEXT = range(3)


def _path(user_id: int) -> str:
    os.makedirs(NOTES_DIR, exist_ok=True)
    return os.path.join(NOTES_DIR, f"notes_{user_id}.json")


def _load(user_id: int) -> list:
    try:
        with open(_path(user_id), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _save(user_id: int, notes: list) -> None:
    with open(_path(user_id), "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def _next_id(notes: list) -> int:
    return max((n["id"] for n in notes), default=0) + 1


def _notes_keyboard(notes: list) -> InlineKeyboardMarkup:
    rows = []
    for note in notes:
        preview = note["text"][:30] + ("…" if len(note["text"]) > 30 else "")
        rows.append([
            InlineKeyboardButton(f"📝 {preview}", callback_data=f"note_view_{note['id']}"),
            InlineKeyboardButton("✏️", callback_data=f"note_edit_{note['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"note_del_{note['id']}"),
        ])
    rows.append([InlineKeyboardButton("➕ הוסף הערה", callback_data="note_add")])
    rows.append([InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")])
    return InlineKeyboardMarkup(rows)


# ── entry ────────────────────────────────────────────────────────────────────

async def show_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()
    uid = update.effective_user.id
    notes = _load(uid)
    text = f"📓 *ההערות שלך* ({len(notes)})" if notes else "📓 *ההערות שלך*\nאין הערות עדיין."
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=_notes_keyboard(notes))


# ── callbacks ────────────────────────────────────────────────────────────────

async def note_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("✏️ שלח את תוכן ההערה החדשה:")
    return ADD_NOTE


async def note_add_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    notes = _load(uid)
    notes.append({"id": _next_id(notes), "text": update.message.text.strip(),
                  "created": datetime.now().strftime("%d/%m/%Y %H:%M")})
    _save(uid, notes)
    await update.message.reply_text("✅ ההערה נשמרה!", reply_markup=_notes_keyboard(notes))
    return ConversationHandler.END


async def note_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    note_id = int(query.data.split("_")[-1])
    notes = _load(uid)
    note = next((n for n in notes if n["id"] == note_id), None)
    if not note:
        await query.answer("ההערה לא נמצאה.", show_alert=True)
        return
    keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await query.message.reply_text(
        f"📝 *הערה #{note_id}*\n_{note['created']}_\n\n{note['text']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def note_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    note_id = int(query.data.split("_")[-1])
    notes = [n for n in _load(uid) if n["id"] != note_id]
    _save(uid, notes)
    text = f"📓 *ההערות שלך* ({len(notes)})" if notes else "📓 *ההערות שלך*\nאין הערות עדיין."
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_notes_keyboard(notes))


async def note_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    note_id = int(query.data.split("_")[-1])
    context.user_data["editing_note_id"] = note_id
    uid = query.from_user.id
    note = next((n for n in _load(uid) if n["id"] == note_id), None)
    if not note:
        await query.answer("ההערה לא נמצאה.", show_alert=True)
        return ConversationHandler.END
    await query.message.reply_text(
        f"✏️ שלח את הטקסט החדש להערה #{note_id}:\n\n_נוכחי:_ {note['text']}",
        parse_mode="Markdown",
    )
    return EDIT_TEXT


async def note_edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    note_id = context.user_data.get("editing_note_id")
    notes = _load(uid)
    for note in notes:
        if note["id"] == note_id:
            note["text"] = update.message.text.strip()
            note["created"] = datetime.now().strftime("%d/%m/%Y %H:%M") + " (עודכן)"
            break
    _save(uid, notes)
    await update.message.reply_text("✅ ההערה עודכנה!", reply_markup=_notes_keyboard(notes))
    return ConversationHandler.END


# ── register ─────────────────────────────────────────────────────────────────

def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(note_add_start, pattern=r"^note_add$"),
            CallbackQueryHandler(note_edit_start, pattern=r"^note_edit_\d+$"),
        ],
        states={
            ADD_NOTE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, note_add_save)],
            EDIT_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, note_edit_save)],
        },
        per_message=False,
        fallbacks=[],
    )
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^הערות$|^הערה$|^רשימת הערות$"), show_notes))
    app.add_handler(CallbackQueryHandler(show_notes, pattern=r"^menu_notes$"))
    app.add_handler(CallbackQueryHandler(note_view,   pattern=r"^note_view_\d+$"))
    app.add_handler(CallbackQueryHandler(note_delete, pattern=r"^note_del_\d+$"))
    app.add_handler(conv)
