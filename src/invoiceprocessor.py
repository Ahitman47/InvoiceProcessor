import logging
from pathlib import Path
from datamodel import ProcessedInvoice

import anthropic
import yaml

import storage
from datetime import datetime
from decisionmaker import DecisionMaker
from extractor import Extractor
from ingest import is_supported, prepare_bytes

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "src" / "config.yaml"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "processed"


class InvoiceProcessor:
    """
    Runs the end-to-end invoice processing flow.
    """

    def __init__(self, processed_invoices: set | None = None):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.max_image_dimension = self.config["processing"]["max_image_dimension"]
        self.extractor = Extractor(self.config)

        # Seed duplicate detection from everything processed in previous runs.
        seen = processed_invoices if processed_invoices is not None else storage.get_all_identities()
        self.decision_maker = DecisionMaker(self.config, processed_invoices=seen)

    async def process_one(self, raw_bytes: bytes, filename: str) -> ProcessedInvoice | None:
        """
        Processes a single file end-to-end: ingestion, extraction, and decisionmaking.
        Writes result to the storage and registers the invoice identity
        """
        try:
            ingested = prepare_bytes(raw_bytes, filename, self.max_image_dimension)
        except Exception as e:
            logger.error("Ingestion failed for %s: %s", filename, e)
            return None
        try:
            extracted = await self.extractor.extract(ingested)
        except (anthropic.APIError, ValueError) as e:
            logger.error("Extraction failed for %s: %s", filename, e)
            return None

        result = self.decision_maker.evaluate(
            extracted,
            source_file=ingested.source_file,
            file_hash=ingested.file_hash
        )

        if extracted.identity:
            self.decision_maker.processed_invoices.add(extracted.identity)

        self.write_output(result)
        return result

    async def process_batch(self, data_dir: Path = DATA_DIR) -> list[ProcessedInvoice]:
        """
        Processes all supported files in the data directory sequentially.
        Returns list of (successfully) ProcessedInvoice results.
        """
        paths = sorted(p for p in data_dir.iterdir() if is_supported(p))

        results = []
        for path in paths:
            result = await self.process_one(path.read_bytes(), path.name)
            if result is not None:
                results.append(result)
        return results

    @staticmethod
    def write_output(result: ProcessedInvoice) -> None:
        """
        Writes a ProcessedInvoice as JSON to the output directory.
        """
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = OUTPUT_DIR / f"{Path(result.source_file).stem}_{timestamp}.json"
        out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")