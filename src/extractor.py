import json
import logging
import yaml
import anthropic
from dotenv import load_dotenv
from pydantic import ValidationError
from pathlib import Path
from anthropic.types import TextBlock

import storage
from datamodel import ExtractedInvoice, IngestedFile
from prompts.extraction import build_prompt, EXTRACTION_PROMPT_VERSION
from prompts.retry import build_retry_prompt

load_dotenv()

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parent.parent / "src" / "config.yaml"

class Extractor:
    """
    Extracts structured invoice data from an ingested file using Claude Vision.

    Supports both PDF and image inputs via the appropriate content type. Checks
    storage first and skips the API call if persisted result exists.

    Retries on invalid or unparseable model output by feeding the error back into
    the next attempt.
    """

    def __init__(self, config: dict):
        self.client = anthropic.AsyncAnthropic(
            max_retries=3,
            timeout=30.0,
        )

        with open(CONFIG_PATH, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.categories = config["categories"]
        self.prompt = build_prompt(self.categories)
        self.model = config["extraction"]["model"]
        self.max_parse_attempts = config["extraction"]["max_parse_attempts"]
        self.temperature = config["extraction"]["temperature"]
        self.max_tokens =  config["extraction"]["max_tokens"]

    async def extract(self, ingested: IngestedFile) -> ExtractedInvoice:
        """
        Extracts an invoice from an ingested file.

        Uses persisted results when available, otherwise calls Claude Vision.
        Retries parsing up to max_parse_attempts timex before failing.

        Raises ValueError if extraction ultimately fails.
        """
        persisted = storage.get(ingested.file_hash)
        if persisted is not None:
            return persisted

        content_block = self.build_content_block(ingested)
        messages = [
            {
                "role": "user",
                "content": [
                    content_block,
                    {"type": "text", "text": self.prompt},
                ],
            }
        ]

        last_error = None
        for attempt in range(1, self.max_parse_attempts + 1):
            raw = await self.call_claude(messages)
            try:
                extracted = self.parse_response(raw)
                storage.save(ingested.source_file, ingested.file_hash, extracted, EXTRACTION_PROMPT_VERSION, extracted.identity)
                return extracted
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_error = e
                logger.warning(
                    "Parse attempt %d/%d failed for %s: %s",
                    attempt, self.max_parse_attempts, ingested.source_file, e
                )
                # message history is kept!!
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": build_retry_prompt(str(e))})

        raise ValueError(
            f"Failed to extract {ingested.source_file} after {self.max_parse_attempts} attempts. "
            f"Last error: {last_error}"
        )

    async def call_claude(self, messages: list) -> str:
        """
        Sends request to Claude and returns raw text of the first TEXT response block (if there is one).
        """
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=messages
        )

        text = next((b.text for b in message.content if isinstance(b, TextBlock)), None)
        if text is None:
            raise ValueError("No text block in response")
        return text

    @staticmethod
    def parse_response(raw: str) -> ExtractedInvoice:
        """
        Parse raw LLM output into an ExtractedInvoice.
        """
        text = raw.strip()

        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError(f"No JSON object found in response:\n{raw}")
            text = text[start:end]

        data = json.loads(text)

        return ExtractedInvoice(**data)

    @staticmethod
    def build_content_block(ingested: IngestedFile) -> dict:
        """
        Builds content block for the given file type.
        Document block for PDFs and an image block for image files.
        """
        if ingested.media_type == "application/pdf":
            return {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": ingested.media_type,
                    "data": ingested.data_base64
                }
            }
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": ingested.media_type,
                "data": ingested.data_base64
            }
        }