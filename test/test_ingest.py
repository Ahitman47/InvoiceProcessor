import sys
import io
import hashlib
import base64
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PIL import Image

from ingest import prepare_bytes, prepare_file, convert_image_to_png, is_supported


def make_image_bytes(width, height, fmt="PNG", mode="RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height)).save(buffer, format=fmt)
    return buffer.getvalue()


def test_hash_is_computed_on_original_bytes():
    raw = make_image_bytes(100, 100)
    result = prepare_bytes(raw, "invoice.png", 1500)
    assert result.file_hash == hashlib.sha256(raw).hexdigest()


def test_pdf_is_passed_through_unchanged():
    raw = b"%PDF-1.4 fake"
    result = prepare_bytes(raw, "invoice.pdf", 1500)
    assert result.media_type == "application/pdf"
    assert base64.b64decode(result.data_base64) == raw


def test_image_is_normalized_to_png():
    raw = make_image_bytes(100, 100, fmt="JPEG")
    result = prepare_bytes(raw, "invoice.jpg", 1500)
    assert result.media_type == "image/png"


def test_filename_is_carried_through():
    result = prepare_bytes(make_image_bytes(50, 50), "scan_007.png", 1500)
    assert result.source_file == "scan_007.png"


def test_large_image_is_downscaled():
    converted = convert_image_to_png(make_image_bytes(3000, 1500), 1500)
    assert max(Image.open(io.BytesIO(converted)).size) == 1500


def test_small_image_is_not_upscaled():
    converted = convert_image_to_png(make_image_bytes(200, 100), 1500)
    assert Image.open(io.BytesIO(converted)).size == (200, 100)


def test_non_rgb_mode_is_converted():
    # CMYK cannot be saved as PNG directly; must be converted to RGB first.
    converted = convert_image_to_png(make_image_bytes(50, 50, fmt="TIFF", mode="CMYK"), 1500)
    assert Image.open(io.BytesIO(converted)).mode in ("RGB", "RGBA", "L")


def test_corrupt_bytes_raise():
    with pytest.raises(Exception):
        convert_image_to_png(b"not an image", 1500)

def test_prepare_file_reads_from_disk(tmp_path):
    raw = make_image_bytes(100, 100)
    path = tmp_path / "invoice.png"
    path.write_bytes(raw)

    result = prepare_file(path, 1500)
    assert result.source_file == "invoice.png"
    assert result.file_hash == hashlib.sha256(raw).hexdigest()

def test_is_supported_true_for_known_extension(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"x")
    assert is_supported(path) is True


def test_is_supported_false_for_unknown_extension(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes(b"x")
    assert is_supported(path) is False


def test_is_supported_false_for_directory(tmp_path):
    assert is_supported(tmp_path) is False
