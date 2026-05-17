import io
import zipfile
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

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


MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB — Telegram Bot API download limit


async def make_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document

    if photo or (doc and doc.mime_type and doc.mime_type.startswith("image/")):
        file_obj = photo or doc

        # Validate file size before attempting download
        file_size = getattr(file_obj, "file_size", None)
        if file_size and file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f"❌ הקובץ גדול מדי ({file_size / 1024 / 1024:.1f}MB).\n"
                "מגבלת Telegram היא 20MB. אנא שלח תמונה קטנה יותר."
            )
            return WAIT_IMAGE

        tg_file = await context.bot.get_file(file_obj.file_id)
        img_bytes = await tg_file.download_as_bytearray()
        
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        except Exception:
            await update.message.reply_text("❌ לא ניתן לקרוא את התמונה. נסה תמונה אחרת.")
            return WAIT_IMAGE

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            # Create .ico file (contains multiple sizes natively if we want, or just save as ico)
            ico_buf = io.BytesIO()
            img.save(ico_buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
            zf.writestr("icon.ico", ico_buf.getvalue())
            
            # Create PNGs of various standard sizes
            sizes = [16, 32, 48, 64, 128, 256, 512]
            for size in sizes:
                png_buf = io.BytesIO()
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                resized.save(png_buf, format="PNG")
                zf.writestr(f"icon_{size}x{size}.png", png_buf.getvalue())

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
