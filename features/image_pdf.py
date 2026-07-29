import io
from pypdf import PdfReader
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from features.media_utils import ImageTooLargeError, load_image, validate_file_size


async def image_to_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document

    # image → PDF
    if photo or (doc and doc.mime_type and doc.mime_type.startswith("image/")):
        file_obj = photo or doc
        try:
            validate_file_size(getattr(file_obj, "file_size", None))
        except ImageTooLargeError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        tg_file = await context.bot.get_file(file_obj.file_id)
        img_bytes = await tg_file.download_as_bytearray()
        try:
            validate_file_size(len(img_bytes))
            img = load_image(img_bytes, "RGB")
        except (ImageTooLargeError, ValueError) as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        pdf_buf = io.BytesIO()
        try:
            img.save(pdf_buf, format="PDF")
        finally:
            img.close()
        pdf_buf.seek(0)
        await update.message.reply_document(
            document=pdf_buf,
            filename="converted.pdf",
            caption="✅ הומר לPDF בהצלחה!",
        )
        return

    # PDF → images (one image per page, using Pillow via PDF rasterization)
    if doc and doc.mime_type == "application/pdf":
        try:
            validate_file_size(getattr(doc, "file_size", None))
        except ImageTooLargeError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        tg_file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await tg_file.download_as_bytearray()
        try:
            validate_file_size(len(pdf_bytes))
        except ImageTooLargeError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        reader = PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        await update.message.reply_text(
            f"📄 PDF עם {num_pages} עמודים.\n"
            "⚠️ המרת PDF לתמונה דורשת Poppler.\n"
            "להתקנה: https://github.com/oschwartz10612/poppler-windows/releases\n"
            "לאחר ההתקנה הוסף לסביבה: `pip install pdf2image` ועדכן את הבוט."
        )


def register(app) -> None:
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, image_to_pdf))
