"""Small, shared guards for user-provided image files.

Telegram's upload size is not a useful memory limit: a tiny compressed PNG can
expand to hundreds of megabytes when Pillow decodes it. Keep the limits here so
all image features enforce the same budget.
"""
import io
import warnings

from PIL import Image, UnidentifiedImageError

MAX_INPUT_FILE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000


class ImageTooLargeError(ValueError):
    """The input would exceed the bot's memory budget."""


def validate_file_size(file_size: int | None) -> None:
    if file_size is not None and file_size > MAX_INPUT_FILE_BYTES:
        raise ImageTooLargeError(
            f"הקובץ גדול מדי. המגבלה היא {MAX_INPUT_FILE_BYTES // 1024 // 1024}MB."
        )


def load_image(image_bytes: bytes | bytearray, mode: str) -> Image.Image:
    """Decode one image only after enforcing a strict decoded-pixel limit."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as source:
                width, height = source.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise ImageTooLargeError(
                        f"התמונה גדולה מדי ({width * height / 1_000_000:.1f}MP). "
                        f"המגבלה היא {MAX_IMAGE_PIXELS / 1_000_000:.0f}MP."
                    )
                source.load()
                return source.convert(mode)
    except ImageTooLargeError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError("ממדי התמונה גדולים מדי לעיבוד.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("לא ניתן לקרוא את התמונה. נסה קובץ JPG או PNG תקין.") from exc
