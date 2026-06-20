import sys
import pytest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

import storage
from datamodel import ExtractedInvoice


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    path = tmp_path / "store.json"
    monkeypatch.setattr(storage, "STORAGE_PATH", path)
    return path


def make_invoice(vendor="Acme Ltd", number="INV-001") -> ExtractedInvoice:
    return ExtractedInvoice(
        vendor=vendor,
        buyer_name="Buyer Co",
        invoice_number=number,
        invoice_date="2023-05-10",
        net_total="100.00",
        vat_total="21.00",
        gross_total="121.00",
        currency="EUR",
        items=[],
        category="other",
    )


def test_get_returns_none_for_unknown_hash(temp_store):
    assert storage.get("does-not-exist") is None


def test_save_then_get_roundtrip(temp_store):
    invoice = make_invoice()
    storage.save("invoice.png", "hash1", invoice, "v1", invoice.identity)

    loaded = storage.get("hash1")
    assert loaded is not None
    assert loaded.vendor == "Acme Ltd"
    assert loaded.gross_total == invoice.gross_total


def test_save_overwrites_same_hash(temp_store):
    storage.save("a.png", "hash1", make_invoice(vendor="First"), "v1", "First-INV-001")
    storage.save("b.png", "hash1", make_invoice(vendor="Second"), "v1", "Second-INV-001")

    loaded = storage.get("hash1")
    assert loaded.vendor == "Second"


def test_get_all_identities_collects_saved(temp_store):
    storage.save("a.png", "h1", make_invoice(vendor="A", number="1"), "v1", "A-1")
    storage.save("b.png", "h2", make_invoice(vendor="B", number="2"), "v1", "B-2")

    assert storage.get_all_identities() == {"A-1", "B-2"}


def test_get_all_identities_skips_none(temp_store):
    storage.save("a.png", "h1", make_invoice(), "v1", "A-1")
    storage.save("b.png", "h2", make_invoice(), "v1", None)

    assert storage.get_all_identities() == {"A-1"}


def test_empty_store_returns_empty_identities(temp_store):
    assert storage.get_all_identities() == set()