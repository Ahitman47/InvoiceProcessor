EXTRACTION_PROMPT_VERSION = "v1"

EXTRACTION_PROMPT = """
You are a data extraction assistant. Extract the following fields from the invoice and return ONLY a valid JSON object — no explanation, no markdown, no code fences.

Fields to extract:
- vendor: string (the seller/supplier name)
- buyer_name: string (the buyer/recipient name)
- invoice_number: string
- invoice_date: string in ISO format (YYYY-MM-DD)
- currency: ISO 4217 currency code (e.g. EUR, USD). Do not use symbols or full names.
- net_total: the total amount excluding VAT as a string (e.g. "100.00")
- vat_total: the total VAT amount as a string (e.g. "21.00")
- gross_total: the total amount including VAT as a string (e.g. "121.00")
- items: a list of line items, each with:
    - description: string
    - quantity: number (can be fractional for hours, weight, etc.)
    - net_price: price per unit excluding VAT, as a string
    - vat_pct: VAT rate applied to this line item as a string (e.g. 0.21 for 21%)
    - line_gross_total: total for this line including VAT, as a string
- category: the single most dominant expense category for this invoice.
    Choose exactly one category from the following allowed list: {categories}
    If multiple categories apply, pick the one that covers the largest share of the invoice value.
    If none fit well, use "other".

Rules:
- If a field is not present or cannot be determined, use null. Only extract information that is explicitly present in the invoice. Do not infer, estimate, or complete missing values.
- All numeric fields must be returned as strings representing decimal numbers (e.g. "100.00", "0.21"). Do not use floats or percentages.
- Dates must be in ISO format: YYYY-MM-DD. If the full date is not explicitly present, return null. Do not guess missing day, month, or year.
- vat_pct must be a string of a fraction (0.21, not 21).
- Return ONLY the JSON object. No text before or after.
- Return all fields even if null. Do not omit fields.
- Keep field names exactly as specified. Do not rename or reorder structure.

Expected JSON structure:
{{
  "vendor": "...",
  "buyer_name": "...",
  "invoice_number": "...",
  "invoice_date": "YYYY-MM-DD",
  "currency": "...",
  "net_total": "...",
  "vat_total": "...",
  "gross_total": "...",
  "items": [
    {{
      "description": "...",
      "quantity": 1.0,
      "net_price": "...",
      "vat_pct": "0.10",
      "line_gross_total": "..."
    }}
  ],
  "category": "..."
}}
"""


def build_prompt(categories: list[str]) -> str:
    """
    Builds the extraction prompt with the allowed categories from the configuration.
    """
    return EXTRACTION_PROMPT.format(categories=", ".join(categories))