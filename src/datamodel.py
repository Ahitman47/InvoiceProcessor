from datetime import date
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field

class IngestedFile(BaseModel):
    """A file ready to send to Claude Vision: bytes encoded, type identified, hash captured."""
    source_file: str
    file_hash: str
    media_type: str           # "application/pdf" or "image/png"
    data_base64: str

class InvoiceItem(BaseModel):
    description: str
    quantity: float | None = None
    net_price: Decimal | None = None
    vat_pct: Decimal | None = None
    line_gross_total: Decimal

class ExtractedInvoice(BaseModel):
    vendor: str | None = None
    buyer_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    net_total: Decimal | None = None
    vat_total: Decimal | None = None
    gross_total: Decimal | None = None
    currency: str | None = None
    items: list[InvoiceItem] = Field(default_factory=list)
    category: str | None = None

    @property
    def identity(self) -> str | None:
        """
        ID used for duplicate detection in the format vendor-invoice_number.
        """
        if not self.vendor or not self.invoice_number:
            return None
        return f"{self.vendor}-{self.invoice_number}"

class Decision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"

class RuleFailure(BaseModel):
    rule_id: str
    explanation: str

class ProcessedInvoice(BaseModel):
    source_file: str
    file_hash: str
    extracted: ExtractedInvoice
    decision: Decision
    failures: list[RuleFailure] = Field(default_factory=list)