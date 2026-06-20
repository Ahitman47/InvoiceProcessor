import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "src"))

import json
import tempfile

import invoiceprocessor
from invoiceprocessor import InvoiceProcessor
from datamodel import ProcessedInvoice, ExtractedInvoice, Decision


def make_processed(source_file="invoice_001.pdf", decision=Decision.ACCEPT) -> ProcessedInvoice:
    return ProcessedInvoice(
        source_file=source_file,
        file_hash="abc123",
        extracted=ExtractedInvoice(vendor="Acme", currency="EUR", items=[]),
        decision=decision,
        failures=[],
    )


def test_write_output_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        invoiceprocessor.OUTPUT_DIR = tmp_dir

        InvoiceProcessor.write_output(make_processed())
        assert len(list(tmp_dir.glob("invoice_001_*.json"))) == 1


def test_write_output_content():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        invoiceprocessor.OUTPUT_DIR = tmp_dir

        InvoiceProcessor.write_output(make_processed(decision=Decision.REJECT))
        file = next(tmp_dir.glob("invoice_001_*.json"))
        data = json.loads(file.read_text(encoding="utf-8"))
        assert data["decision"] == "reject"
        assert data["source_file"] == "invoice_001.pdf"