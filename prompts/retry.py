RETRY_PROMPT_VERSION = "v1"

RETRY_PROMPT = """
Your previous response could not be parsed as valid JSON matching the required schema.

Error: {error}

Return ONLY the JSON object, with all required fields, correctly typed.
No explanation, no markdown, no code fences. Start your response with {{ and end with }}.
"""


def build_retry_prompt(error: str) -> str:
    """
    Builds a retry prompt for a failed extraction attempt. Includes prev error as well.
    """
    return RETRY_PROMPT.format(error=error)