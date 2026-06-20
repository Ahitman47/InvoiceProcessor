import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "src"))

import json
import pytest

from extractor import Extractor
from datamodel import IngestedFile


def test_parses_clean_json():
    raw = '{"vendor": "Acme", "currency": "EUR", "items": []}'
    result = Extractor.parse_response(raw)
    assert result.vendor == "Acme"
    assert result.currency == "EUR"


def test_strips_surrounding_text():
    raw = 'Here is the data: {"vendor": "Acme", "items": []} done.'
    result = Extractor.parse_response(raw)
    assert result.vendor == "Acme"


def test_handles_markdown_fenced_json():
    raw = '```json\n{"vendor": "Acme", "items": []}\n```'
    result = Extractor.parse_response(raw)
    assert result.vendor == "Acme"


def test_no_json_raises():
    with pytest.raises(ValueError):
        Extractor.parse_response("no json here at all")


def test_invalid_schema_raises():
    # gross_total must be a valid Decimal; "abc" should fail Pydantic validation
    raw = '{"vendor": "Acme", "gross_total": "abc", "items": []}'
    with pytest.raises((ValueError, json.JSONDecodeError)):
        Extractor.parse_response(raw)


def test_pdf_builds_document_block():
    ingested = IngestedFile(source_file="a.pdf", file_hash="h",
                            media_type="application/pdf", data_base64="ZmFrZQ==")
    block = Extractor.build_content_block(ingested)
    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"


def test_image_builds_image_block():
    ingested = IngestedFile(source_file="a.png", file_hash="h",
                            media_type="image/png", data_base64="ZmFrZQ==")
    block = Extractor.build_content_block(ingested)
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"