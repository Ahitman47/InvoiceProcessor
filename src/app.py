import sys
from pathlib import Path
from contextlib import asynccontextmanager

SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
EVAL_DIR = ROOT_DIR / "eval"
sys.path.append(str(EVAL_DIR))
sys.path.append(str(SRC_DIR))
sys.path.append(str(ROOT_DIR))

from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

import storage
from invoiceprocessor import InvoiceProcessor
from evaluation import evaluate

processor: InvoiceProcessor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global processor
    processor = InvoiceProcessor()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    """Serves the upload page."""
    return FileResponse(SRC_DIR / "index.html")


@app.post("/process")
async def process(file: UploadFile):
    """Processes one uploaded invoice end-to-end and returns the decision as JSON."""
    raw_bytes = await file.read()
    result = await processor.process_one(raw_bytes, file.filename)

    if result is None:
        return JSONResponse(
            status_code=422,
            content={"error": f"Could not process '{file.filename}'. The file may be unreadable or extraction failed."},
        )

    return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/evaluate")
async def run_evaluation():
    """
    Runs the full evaluation against the labelled set and returns the report as plain text.
    """

    report_path = await evaluate()  # evaluate() must return the written report Path
    return PlainTextResponse(report_path.read_text(encoding="utf-8"))


@app.post("/empty-store")
async def empty_store():
    """
    Clears the persistent store: extraction cache and duplicate identities.
    After this, the next run re-extracts every invoice and detects no duplicates.
    """
    storage.empty_storage()
    processor.decision_maker.processed_invoices.clear()
    return JSONResponse(content={"status": "store emptied"})