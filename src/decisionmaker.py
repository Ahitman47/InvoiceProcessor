from decimal import Decimal

from datamodel import (
    Decision,
    ExtractedInvoice,
    ProcessedInvoice,
    RuleFailure,
)

class DecisionMaker:
    """
    Evaluates invoices against configured validation rules.

    All rule violations are collected and returned together instead of stopping
    at the first failure, to support full auditability.

    The processed_invoices set is used to detect duplicates.
    """
    def __init__(self, config: dict, processed_invoices: set[str] | None = None):
        self.currency_cfg = config["currency"]
        self.rules = config["rules"]

        # we set an id of a processed_invoice to be "{vendor}-{invoice_number}"
        # because we can't guarantee different vendors to use different invoices numbers
        self.processed_invoices = processed_invoices or set()

    def convert_to_base(self, amount: Decimal, currency: str) -> Decimal:
        """
        Converts an amount to the base currency (EUR) using the configured exchange rate.
        If currency is already the base currency, original amount is returned unchanged.
        """
        if currency == self.currency_cfg["base"]:
            return amount

        rate = Decimal(str(self.currency_cfg["rates"][currency]))
        return amount * rate

    def evaluate(self, invoice: ExtractedInvoice, source_file: str, file_hash: str) -> ProcessedInvoice:
        """
        Runs all business rules against a single invoice and produces the final decision.

        Validation is done in stages:
           basic gate checks (currency, required fields)
           conditional amount checks (only when currency is valid and conversion is possible)

        This ensures dependent rules are only evaluated once their prerequisites are met.
        """
        failures: list[RuleFailure] = []

        currency_accepted = invoice.currency in self.currency_cfg["accepted"]
        if not currency_accepted:
            failures.append(RuleFailure(
                rule_id="currency",
                explanation=f"Currency '{invoice.currency}' is missing or not accepted {self.currency_cfg['accepted']}"
            ))

        missing_fields = [f for f in self.rules["required_fields"]
                          if getattr(invoice, f) is None]

        if missing_fields:
            failures.append(RuleFailure(
                rule_id="required_fields",
                explanation=f"Missing required field(s): {', '.join(missing_fields)}"
            ))

        if (invoice.invoice_date and
                invoice.invoice_date.year < self.rules["min_invoice_year"]):
            failures.append(RuleFailure(
                rule_id="min_invoice_year",
                explanation=f"Invoice year {invoice.invoice_date.year} is before {self.rules['min_invoice_year']}"
            ))

        if currency_accepted:
            self.check_item_amounts(invoice, failures)
            self.check_line_totals(invoice, failures)
            self.check_invoice_total(invoice, failures)

        self.check_duplicate(invoice, failures)

        return ProcessedInvoice(
            source_file=source_file,
            file_hash=file_hash,
            extracted=invoice,
            decision=Decision.REJECT if failures else Decision.ACCEPT,
            failures=failures
        )

    def check_item_amounts(self, invoice: ExtractedInvoice, failures: list[RuleFailure]):
        """
        Checks each line item and flags any items that exceed the per-item limit (in base currency).
        A RuleFailure is appended for every offending item.
        """
        for item in invoice.items:
            amount = self.convert_to_base(
                item.line_gross_total, # description/requierement was unclear whether a unit price or total price for an item x quantity
                invoice.currency # make sure to always check for currency before calling this function otherwise error
            )

            if amount <= self.rules["max_item_amount"]:
                continue

            failures.append(RuleFailure(
                rule_id="max_item_amount",
                explanation=f"Item '{item.description}' totals {amount:.2f} EUR, over limit {self.rules['max_item_amount']}"
            ))

    def check_line_totals(self, invoice: ExtractedInvoice, failures: list[RuleFailure]):
        """
        Checks whether the sum of line item totals matches the invoice gross total within the configured tolerance.
        Skipped if gross_total or items are missing.
        Appends RuleFailure when difference exceeds allowed tolerance.
        """
        if invoice.gross_total is None or not invoice.items:
            return

        line_total = sum((item.line_gross_total for item in invoice.items), Decimal("0"))

        difference = abs(line_total - invoice.gross_total)
        tolerance = Decimal(str(self.rules["line_total_tolerance"]))

        if difference <= tolerance:
            return

        failures.append(RuleFailure(
            rule_id="line_total_tolerance",
            explanation=f"Line totals sum to {line_total} but gross_total is {invoice.gross_total} (off by {difference})"
        ))

    def check_invoice_total(self, invoice: ExtractedInvoice, failures: list[RuleFailure]):
        """
        Checks whether the invoice gross total exceeds the configured maximum.
        The amount is converted to the base currency before comparison.
        """
        if invoice.gross_total is None:
            return

        total = self.convert_to_base(invoice.gross_total, invoice.currency )

        if total <= self.rules["max_total_amount"]:
            return

        failures.append(RuleFailure(
            rule_id="max_total_amount",
            explanation=f"Gross total {total:.2f} EUR exceeds limit {self.rules['max_total_amount']}"
        ))

    def check_duplicate(self, invoice: ExtractedInvoice, failures: list[RuleFailure]):
        """
        Checks whether an invoice has already been processed.
        Invoices are identified by vendor-invoice_number.
        """
        if not invoice.vendor or not invoice.invoice_number:
            return

        identity = f"{invoice.vendor}-{invoice.invoice_number}"

        if identity not in self.processed_invoices:
            return

        failures.append(RuleFailure(
            rule_id="duplicate",
            explanation=f"Invoice '{identity}' has already been processed"
        ))