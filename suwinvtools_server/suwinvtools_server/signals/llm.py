"""The language model: reads documents the job fetched and returns what they say, as JSON.

It never knows anything on its own. Every claim carries the words it rests on, and `verify`
checks them against the documents deterministically: words that are not there, or a number
the words do not contain, and the claim is dropped. The model can only ever make a reading
INVALID, never invent one.

Any OpenAI-compatible endpoint works (vLLM, Ollama, OpenRouter, …) through LiteLLM's
`openai/` provider; structured output comes from `response_format` with the pydantic schema.
"""

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from suwinvtools_server.settings import Settings
from suwinvtools_server.signals.model import Evidence, Quote


@dataclass(frozen=True)
class Document:
    id: str  # what a quote cites: "d1", "n3", …
    title: str
    url: str
    text: str


class LlmError(RuntimeError):
    """No model is configured, or it did not return the schema."""


# schema, instruction, documents -> the filled schema. The job uses `litellm_extractor`; the
# tests pass a stub that returns a ready answer.
type Extractor = Callable[[type[BaseModel], str, Sequence[Document]], BaseModel]

SYSTEM = """You extract facts from the documents you are given. Rules:
- Use ONLY the documents. If they do not state something, say so (found=false, or an empty list).
- Every quote is copied VERBATIM from the document whose id you give — same words, same numbers.
- Never compute, estimate or round a number the documents do not state.
- Answer with JSON that matches the schema, nothing else."""


def prompt(instruction: str, documents: Sequence[Document]) -> str:
    parts = [instruction, ""]
    parts.extend(f'<document id="{doc.id}" title="{doc.title}">\n{doc.text}\n</document>' for doc in documents)
    return "\n".join(parts)


def litellm_extractor(settings: Settings) -> Extractor:
    if not settings.llm_base_url or not settings.llm_model:
        raise LlmError("LLM_BASE_URL and LLM_MODEL are not set — `just signals init` asks for them")

    def extract(schema: type[BaseModel], instruction: str, documents: Sequence[Document]) -> BaseModel:
        import litellm  # noqa: PLC0415 — heavy (a second of imports); only the job's LLM checks pay for it

        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(instruction, documents)}]
        extra: dict[str, object] = {}
        if settings.llm_disable_thinking:
            extra["chat_template_kwargs"] = {"enable_thinking": False}
        last_error = ""
        for attempt in range(2):
            if attempt:
                # One retry with the validation error in front of the model, then give up.
                messages.append({"role": "user", "content": f"Your answer did not match the schema: {last_error}. Answer again."})
            try:
                response: Any = litellm.completion(
                    model=f"openai/{settings.llm_model}",
                    api_base=settings.llm_base_url,
                    api_key=settings.llm_api_key or "dummy",
                    messages=messages,
                    response_format=schema,
                    temperature=0,
                    timeout=120,
                    extra_body=extra or None,
                )
            except Exception as exc:  # litellm raises its own zoo of errors; all of them mean "no answer"
                raise LlmError(f"{settings.llm_model} at {settings.llm_base_url}: {exc}") from exc
            content = cast(str | None, response.choices[0].message.content)
            try:
                return schema.model_validate_json(_json_part(content or ""))
            except ValidationError as exc:
                last_error = str(exc)[:500]
        raise LlmError(f"{settings.llm_model} did not return {schema.__name__}: {last_error}")

    return extract


def _json_part(content: str) -> str:
    """The JSON object in an answer — some servers wrap it in a ``` fence despite the schema."""
    start, end = content.find("{"), content.rfind("}")
    return content[start : end + 1] if start != -1 and end > start else content


# --- verification -----------------------------------------------------------------------------


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    quotes = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "}
    text = text.translate(str.maketrans(quotes))
    return re.sub(r"\s+", " ", text).strip().lower()


def verify(quote: Quote | None, documents: Sequence[Document]) -> Evidence | None:
    """The evidence a quote is, when its words really are in the document it cites."""
    if quote is None or len(quote.text.split()) < 3:
        return None
    document = next((doc for doc in documents if doc.id == quote.source_id), None)
    if document is None or normalize(quote.text) not in normalize(document.text):
        return None
    return Evidence(url=document.url, title=document.title, quote=quote.text.strip())


_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|percent|trillion|tn|billion|bn|b\b|million|mn|m\b|quadrillion|thousand|k\b)?", re.I)
_SCALES = {
    "thousand": 1e3,
    "k": 1e3,
    "million": 1e6,
    "mn": 1e6,
    "m": 1e6,
    "billion": 1e9,
    "bn": 1e9,
    "b": 1e9,
    "trillion": 1e12,
    "tn": 1e12,
    "quadrillion": 1e15,
}


def states_number(text: str, value: float, *, tolerance: float = 0.01) -> bool:
    """Whether `text` contains `value`, written plainly or with a unit word ("$5.2 billion",
    "39%", "five-year" does not count). Used so a correct quote cannot carry a wrong number."""
    if value == 0:
        return True
    for match in _NUMBER.finditer(text):
        number = float(match.group(1).replace(",", ""))
        unit = (match.group(2) or "").lower()
        candidates = [number, number * _SCALES.get(unit, 1.0)]
        if any(abs(candidate - value) <= tolerance * abs(value) for candidate in candidates):
            return True
    return False
