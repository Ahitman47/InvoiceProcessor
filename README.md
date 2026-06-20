# Invoice Processing System

Implementation of the invoice processing take-home assignment for the KPN AI Engineer role.

Takes an invoice (PDF or image), extracts the fields, assigns a category, and applies the approval
rules to give an ACCEPT or REJECT decision with reasons. Output is JSON, and there's a minimal web app
to upload a file and see the result.

## How to run

```
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

cd src
uvicorn app:app --reload
```

Open http://localhost:8000.

No API key needed to try it. The repo includes a populated `storage.json` with the extractions for
all provided invoices, so uploading one (of the provided invoices / running the evaluation) matches on the file hash and
returns the cached result without calling the LLM. To run extraction live (e.g. on a new invoice),
add a `.env` in the project root with `ANTHROPIC_API_KEY=your-key-here`.

The web app can process an upload (any invoice, not just the provided), run the evaluation on all invoices (in 'data/'), and reset the store.

## Assignment Requirements

**Ingest PDFs and images.** `ingest.py` reads the bytes and prepares them. PDFs pass through; images
are converted to PNG (Claude Vision doesn't support all image types) and downscaled to a configurable 
max size (saves tokens, keeps digits legible). The hash is taken on the original bytes so it's stable 
as a cache key.

**Extract the fields.** `extractor.py` sends the document to Claude Vision and parses the JSON into a
Pydantic model. I chose Vision over OCR or template/regex: the invoices share a layout, but for a
finance system I don't assume future ones will. Templates break on layout changes, and OCR adds an
error source and loses table structure.  The downside is no per-field confidence, which the deterministic checks cover afterwards.

**Categorize.** The assignment doesn't define the categories, so I picked a small set based on the
invoices and put them in the config (can be adjusted). It runs in the same LLM call as the extraction to avoid a second
request. Mixed invoices get the dominant category, and anything outside the list falls back to `other`.

**Approval rules with explanations.** All six rules are in `decisionmaker.py`, deterministic, with
thresholds in `config.yaml`.It checks in stages: currency and required fields first, followed by the amount-related rules.
All failures are collected rather than stopping at the first (audit reasons), since the assignment wants the reasons
behind a rejection. Each is a `RuleFailure` with a machine-readable id and a human-readable explanation.

**JSON output.** Each processed invoice is written to `output/processed/`, and `/process` returns the
same object. The UI shows that JSON.

**Interface.** Minimal FastAPI web app, built once at startup and reused per request.

## Design decisions

**Components plus an orchestrator.** Ingest, extractor, storage, decision engine, and data model each
do one thing, wired together by the invoice processor. Each part stays testable and replaceable.

**Pydantic for validation.** All extracted data passes through Pydantic models before entering the decision engine. 
This catches malformed LLM output early and ensures the `decisionmaker` always works with validated data types.

**Extraction and decision are strictly separate.** The LLM produces structured data; a deterministic engine
applies the rules. Reflected in two models: `ProcessedInvoice` holds an `ExtractedInvoice` plus the
decision (composition).

**Currency.** Invoices are USD, rules are in EUR, so I convert with a fixed rate from the config (added
as a rule above the six given ones); missing or unsupported currency is rejected. The fixed rate is a
snapshot; in production a live rate would be used ofcourse.

**Two identities.** A byte-hash (sha256 of the file) is the cache key, so I don't pay to extract the
same bytes twice. A content identity (`vendor-invoice_number`) drives duplicate detection for rule 6.
They differ on purpose: two scans of the same invoice have different hashes but the same content
identity. Caching saves API calls; rule 6 is a business rule, and I register the identity on every
processing (accept and reject). I reject every repeat regardless of the earlier outcome, since
otherwise an invoice could be re-submitted with tweaked values until it slips through.

**Local JSON store.** A local JSON file handles both duplicate detection and extraction caching. No external DB, 
since that'd only make the project harder to run and test for someone else. So it isn't concurrency-safe, 
but not more than one person is expected to run it anyway.

**Versioned prompts.** Prompts live in `prompts/` with a version constant, stored alongside each cached
extraction (`prompt_version`) so output is traceable to the prompt that made it.

**Reproducibility.** The real Claude API is used, with a pre-filled store so it runs without a key (for the given invoices).
If the storage is cleared and no API key is configured, new invoices cannot be extracted and processing will fail.
An MP4 file is uploaded in the root folder which shows the web app working.

## Assumptions and limitations

- **Rule 5 ("item amount > €200")** read as the line total (quantity × price, incl. VAT), not unit
  price. The wording is ambiguous, so it's a documented choice.
- **Categorization is invoice-level**; mixed invoices get the dominant category. Per-item would be an
  extension.
- **No invoice number, no content identity**, so it can't be deduplicated. I didn't add a hard reject
  for it, since it isn't one of the six given rules and could interfere with the company's own test cases.
- **Fixed exchange rate**, not live.
- **JSON store isn't concurrency-safe** (full-file rewrite).

## Testing and evaluation

I wrote the evaluation sets before the system, so there was a concrete target. `rules_eval_set.json`
exercises every rule and edge case against the `DecisionMaker`; `pipeline_eval_set.json` measures
end-to-end extraction and decision accuracy against hand-labelled ground truth (all 17 invoices).

The evaluation runs the real `InvoiceProcessor` end-to-end and reports per-field accuracy, item-level
accuracy, accuracy by file type, decision accuracy, and an aggregate financial consistency check (sum
of all line totals vs sum of all gross totals). Reports are saved in `output/evaluation_results/`.

It caught real issues: a systematic date error where the model swaps month and day on some formats, and
two bugs in my own ground truth (item count as `len(items)` instead of per-item quantity, and VAT
labelled `10.0` instead of `0.10`).

Unit tests for the deterministic, API-free parts (`ingest`, `storage`, `decisionmaker`, parsing) are under `test/`. 
Given the time constraints, most were generated from the existing code and then reviewed manually. 
They cover the main behaviours but not every edge case, so some gaps likely remain. 
The extractor itself is validated through the end-to-end evaluation rather than mocked unit tests.

## Project layout

```
data/                       provided invoices
eval/
  evaluation.py             end-to-end evaluation
  pipeline_eval_set.json    ground truth: extraction + decision
  rules_eval_set.json       rule and edge cases
output/
  evaluation_results/       evaluation reports
  processed/                one JSON per processed invoice
  storage/storage.json      the store (cache + identities)
prompts/
  extraction.py             extraction prompt (versioned)
  retry.py                  retry/correction prompt
src/
  app.py                    FastAPI web app
  config.yaml               rules, thresholds, currency, model
  datamodel.py              Pydantic models
  decisionmaker.py          rule engine
  extractor.py              Vision extraction + parse/retry
  index.html                upload UI
  ingest.py                 ingestion / normalization
  invoiceprocessor.py       orchestrator
  storage.py                JSON store
test/                       unit tests
Invoice Processing Use Case.pdf
invoice_processor.mp4       demo video
requirements.txt
```

Model is `claude-haiku-4-5`, configurable in `config.yaml` with the rules, thresholds, currency rate,
and extraction settings.
