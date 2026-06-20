import json
from pathlib import Path
from typing import Any

from datamodel import ExtractedInvoice

STORAGE_PATH = Path(__file__).resolve().parent.parent / "output" / "storage" / "storage.json"


def load_storage() -> dict[str, Any]:
    """
    Loads persisted storage state; returns empty set if it doesn't exist/is empty.
    """
    if not STORAGE_PATH.exists() or not STORAGE_PATH.read_text(encoding="utf-8").strip():
        return {}
    with open(STORAGE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_storage(storage: dict[str, Any]) -> None:
    """
    Writes full storage back to disk.
    """
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STORAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(storage, f, indent=2, default=str)


def get(file_hash: str) -> ExtractedInvoice | None:
    """
    Retrieves cached invoice by file hash if found, otherwise None.
    """
    storage = load_storage()
    entry = storage.get(file_hash)
    if entry is None:
        return None
    return ExtractedInvoice(**entry["extracted"])


def save(file_name: str, file_hash: str, extracted: ExtractedInvoice,
         prompt_version: str, identity: str | None) -> None:
    """
    Stores an extracted invoice in persistent storage under its file hash (for caching)
    Also persists the content identity (vendor-invoice_number) for duplicate detection.
    """
    storage = load_storage()
    storage[file_hash] = {
        "file_name" : file_name,
        "prompt_version": prompt_version,
        "identity": identity,
        "extracted": json.loads(extracted.model_dump_json()),
    }
    save_storage(storage)


def get_all_identities() -> set[str]:
    """
    Extracts stored content identities.
    Returns set not none of vendor-invoice_number values.
    """
    storage = load_storage()
    return {
        entry["identity"]
        for entry in storage.values()
        if entry.get("identity") is not None
    }

def empty_storage() -> None:
    """
    Clear entire storage (extraction cache + duplicate identities).
    """
    save_storage({})

def clear_identities() -> None:
    """
    Sets every stored identity to None, keeping the extraction intact.
    allows storage to be committed after eval so system runs without an API key,
    without duplicate detection at first upload.
    """
    storage = load_storage()
    for entry in storage.values():
        entry["identity"] = None
    save_storage(storage)