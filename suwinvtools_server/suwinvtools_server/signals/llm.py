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
- Answer with compact JSON on one line that matches the schema, nothing else."""


MAX_TOKENS = 800
TIMEOUT_SECONDS = 60


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
                    # Grammar-constrained decoding can loop (endless digits of a float, endless
                    # spaces); without a cap one answer runs until the context is full. Every
                    # schema here fits in a few hundred tokens.
                    max_tokens=MAX_TOKENS,
                    timeout=TIMEOUT_SECONDS,
                    num_retries=0,
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
    """The JSON object in an answer — some servers wrap it in a ``` fence despite the schema —
    repaired when the model looped on whitespace and the token cap cut it off."""
    start = content.find("{")
    if start == -1:
        return content
    return close_truncated(content[start:].rstrip())


def close_truncated(text: str) -> str:
    """`text` cut back to its last complete value and closed with the brackets still open.

    Grammar-constrained decoding sometimes ends a list with thousands of newlines until the cap
    cuts the answer mid-item. What came before that is valid; dropping the unfinished item and
    closing the brackets keeps it. Every claim still has to pass `verify`, so a repair can only
    lose a claim, never invent one. Complete JSON comes back unchanged."""
    stack: list[str] = []
    in_string = escaped = False
    cut, cut_stack = -1, list[str]()
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]" and stack:
            stack.pop()
            if not stack:
                return text[: index + 1]
            cut, cut_stack = index + 1, list(stack)
    if cut == -1:
        return text
    return text[:cut] + "".join(reversed(cut_stack))


# --- verification -----------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Words and numbers only, lower case: a quote from a table ("servers and network equipment,
    two to six years") must match the cells it came from, whatever separates them."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w%$.]+", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # a full stop is punctuation; 4.5 stays a number
    return re.sub(r"\s+", " ", text).strip()


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


_NUMBER_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
    "twenty"
)
_WORDS = {word: index for index, word in enumerate(_NUMBER_WORDS.split(" "))}


def states_number(text: str, value: float, *, tolerance: float = 0.01) -> bool:
    """Whether `text` contains `value`, written plainly or with a unit word ("$5.2 billion",
    "39%", "six years"). Used so a correct quote cannot carry a wrong number."""
    if value == 0:
        return True
    # "six years", "five-year": the filings spell small numbers out.
    text = re.sub(r"\b(" + "|".join(_WORDS) + r")\b", lambda match: str(_WORDS[match.group(1).lower()]), text, flags=re.IGNORECASE)
    for match in _NUMBER.finditer(text):
        number = float(match.group(1).replace(",", ""))
        unit = (match.group(2) or "").lower()
        candidates = [number, number * _SCALES.get(unit, 1.0)]
        if any(abs(candidate - value) <= tolerance * abs(value) for candidate in candidates):
            return True
    return False
