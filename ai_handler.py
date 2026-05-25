import logging
import json
from typing import Dict, Any

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL


logger = logging.getLogger(__name__)


INTENT_ROUTING_SYSTEM_PROMPT = (
    "You are an enterprise-grade intent classification router. "
    "Analyze the user input and map it strictly to one of these intents: "
    "'BOOKING', 'LEAD_INQUIRY', or 'UNKNOWN'. "
    "Extract key entities if present (names, times, services, notes). "
    "Output ONLY a valid JSON object with keys: 'intent' and 'entities'."
)


def classify_incoming_intent(
    incoming_message: str,
    system_prompt: str = INTENT_ROUTING_SYSTEM_PROMPT,
) -> Dict[str, Any]:
    """
    Deterministically classify intent and extract entities as structured JSON.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Please set it in your environment.")

    client = OpenAI(api_key=OPENAI_API_KEY)

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": incoming_message},
            ],
            temperature=0.0,
        )
    except Exception as error:  # OpenAI can raise multiple exception types.
        logger.exception("OpenAI intent extraction call failed.")
        raise RuntimeError(f"OpenAI API call failed: {error}") from error

    if not response.choices:
        raise RuntimeError("OpenAI returned no intent choices.")

    raw_content = response.choices[0].message.content
    if not raw_content:
        raise RuntimeError("OpenAI returned an empty intent payload.")

    try:
        parsed_result = json.loads(raw_content)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"OpenAI returned invalid JSON: {error}") from error

    intent = str(parsed_result.get("intent", "UNKNOWN")).upper()
    if intent not in {"BOOKING", "LEAD_INQUIRY", "UNKNOWN"}:
        intent = "UNKNOWN"

    entities = parsed_result.get("entities", {})
    if not isinstance(entities, dict):
        entities = {}

    return {
        "intent": intent,
        "entities": entities,
    }


def extract_caller_intent(
    incoming_message: str,
    system_prompt: str = INTENT_ROUTING_SYSTEM_PROMPT,
) -> Dict[str, Any]:
    """
    Backward-compatible alias for older imports.
    """
    return classify_incoming_intent(incoming_message, system_prompt=system_prompt)

