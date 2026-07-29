import io
import zipfile
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from features.media_utils import ImageTooLargeError, load_image, validate_file_size

WAIT_IMAGE = 1

async def ask_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")]]
    await query.edit_message_text(
        "🖼️ *יצירת סט אייקונים*\nשלח תמונה (כקובץ או כתמונה רגילה) ואני אהפוך אותה לסט אייקונים בפורמטים וגדלים שונים בקובץ ZIP:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAIT_IMAGE


async def make_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document

    if photo or (doc and doc.mime_type and doc.mime_type.startswith("image/")):
        file_obj = photo or doc

        file_size = getattr(file_obj, "file_size", None)
        try:
            validate_file_size(file_size)
        except ImageTooLargeError as exc:
            await update.message.reply_text(
                f"❌ {exc}\nאנא שלח תמונה קטנה יותר."
            )
            return WAIT_IMAGE

        tg_file = await context.bot.get_file(file_obj.file_id)
        img_bytes = await tg_file.download_as_bytearray()
        try:
            validate_file_size(len(img_bytes))
            img = load_image(img_bytes, "RGBA")
        except (ImageTooLargeError, ValueError) as exc:
            await update.message.reply_text(f"❌ {exc}")
            return WAIT_IMAGE

        try:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                with io.BytesIO() as ico_buf:
                    img.save(ico_buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
                    zf.writestr("icon.ico", ico_buf.getvalue())

                for size in (16, 32, 48, 64, 128, 256, 512):
                    with img.resize((size, size), Image.Resampling.LANCZOS) as resized:
                        with io.BytesIO() as png_buf:
                            resized.save(png_buf, format="PNG")
                            zf.writestr(f"icon_{size}x{size}.png", png_buf.getvalue())
        finally:
            img.close()

        zip_buf.seek(0)
        
        keyboard = [
            [InlineKeyboardButton("🔄 צור עוד אייקונים", callback_data="menu_icon")],
            [InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")],
        ]
        
        await update.message.reply_document(
            document=zip_buf,
            filename="icons.zip",
            caption="✅ מארז האייקונים שלך מוכן!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ אנא שלח תמונה (JPG/PNG).")
        return WAIT_IMAGE


def register(app) -> None:
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_image, pattern=r"^menu_icon$")],
        states={
            WAIT_IMAGE: [MessageHandler(filters.PHOTO | filters.Document.ALL, make_icon)]
        },
        fallbacks=[],
    )
    app.add_handler(conv)
