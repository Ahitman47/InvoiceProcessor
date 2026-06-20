import base64
import hashlib
import io
import logging
from pathlib import Path
from PIL import Image
from datamodel import IngestedFile

logger = logging.getLogger(__name__)

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".tif", ".bmp"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS


def convert_image_to_png(raw_bytes: bytes, max_dimension: int) -> bytes:
    """
    Loads image and scales it down if needed (to save tokens), and returns it as PNG bytes.
    """
    image = Image.open(io.BytesIO(raw_bytes))

    if image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGB")

    image.thumbnail((max_dimension, max_dimension))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def prepare_bytes(raw_bytes: bytes, filename: str, max_image_dimension: int) -> IngestedFile:
    """
    Prepares raw file bytes for an AI model (using Claude Vision).

    Images are normalized (PNG) before upload, while PDFs are passed through
    unchanged. Original file content is used for hash generation.
    """
    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    extension = Path(filename).suffix.lower()

    if extension in PDF_EXTENSIONS:
        data_bytes = raw_bytes
        media_type = "application/pdf"
    else:
        data_bytes = convert_image_to_png(raw_bytes, max_image_dimension)
        media_type = "image/png"

    return IngestedFile(
        source_file=filename,
        file_hash=file_hash,
        media_type=media_type,
        data_base64=base64.b64encode(data_bytes).decode("utf-8"),
    )


def prepare_file(path: Path, max_image_dimension: int) -> IngestedFile:
    """
    Reads a file from disk and prepares it.
    """
    return prepare_bytes(path.read_bytes(), path.name, max_image_dimension)


def is_supported(path: Path) -> bool:
    """
    True if the file is a supported type.
    """
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS