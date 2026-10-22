import pytest

from suwinvtools_server.settings import Settings
from suwinvtools_server.signals.llm import Document, LlmError, close_truncated, litellm_extractor, normalize, states_number, verify
from suwinvtools_server.signals.model import Quote

DOCUMENT = Document(
    id="n1",
    title="Reuters: OpenAI",
    url="https://example.com/a",
    text="OpenAI said its annualized revenue reached “$12 billion” in September,\nup from $6 billion.",
)


def test_normalize_keeps_words_and_numbers_only() -> None:
    messy = "  It\N{RIGHT SINGLE QUOTATION MARK}s  \N{LEFT DOUBLE QUOTATION MARK}A\N{RIGHT DOUBLE QUOTATION MARK}"
    messy += "\N{EM DASH}B\N{NO-BREAK SPACE}C\n D "
    assert normalize(messy) == "it s a b c d"


def test_verify_accepts_words_that_are_in_the_document_it_cites() -> None:
    evidence = verify(Quote(source_id="n1", text='annualized revenue reached "$12 billion" in September'), [DOCUMENT])
    assert evidence is not None
    assert (evidence.url, evidence.title) == (DOCUMENT.url, DOCUMENT.title)
    assert evidence.quote == 'annualized revenue reached "$12 billion" in September'
    # Line breaks and capitals of the document do not matter.
    assert verify(Quote(source_id="n1", text="IN SEPTEMBER, up from $6 billion"), [DOCUMENT]) is not None


@pytest.mark.parametrize(
    "quote",
    [
        None,
        Quote(source_id="n1", text="annualized revenue reached $20 billion in September"),  # words that are not there
        Quote(source_id="n2", text="annualized revenue reached $12 billion"),  # a document that was not sent
        Quote(source_id="n1", text="OpenAI said"),  # too short to prove anything
    ],
)
def test_verify_rejects_invented_misattributed_and_tiny_quotes(quote: Quote | None) -> None:
    assert verify(quote, [DOCUMENT]) is None


@pytest.mark.parametrize(
    ("text", "value", "expected"),
    [
        ("revenue grew 39% year over year", 39, True),
        ("revenue grew 39.2%", 39, True),  # within 1 %
        ("revenue grew 41%", 39, False),
        ("raised $5.2 billion", 5.2e9, True),
        ("raised 5.2 bn", 5.2e9, True),
        ("raised $300 million", 3e8, True),
        ("processes 1.3 quadrillion tokens", 1.3e15, True),
        ("worth $1,250,000 in total", 1.25e6, True),
        ("a five-year plan", 5, True),  # filings spell small numbers out
        ("a 5-year plan", 5, True),
        ("raised $40 billion at a $300 billion valuation", 300e9, True),
        ("raised $40 billion", 300e9, False),
        ("no numbers here", 12, False),
        ("anything", 0, True),
    ],
)
def test_states_number(text: str, value: float, expected: bool) -> None:
    assert states_number(text, value) is expected


def test_the_extractor_needs_a_configured_model() -> None:
    with pytest.raises(LlmError, match="LLM_BASE_URL"):
        litellm_extractor(Settings(llm_base_url="", llm_model=""))


def test_a_truncated_list_keeps_its_complete_items() -> None:
    looped = '{"events":[{"x":"a}b"},{"x":"c"}, {"x":"unfin'

    assert close_truncated(looped) == '{"events":[{"x":"a}b"},{"x":"c"}]}'


def test_a_list_ended_by_whitespace_until_the_cap_is_closed() -> None:
    assert close_truncated('{"claims":[{"q":{"t":"x"}}' + "\n" * 50) == '{"claims":[{"q":{"t":"x"}}]}'


def test_complete_json_is_left_as_it_is() -> None:
    assert close_truncated('{"a": 1} trailing words') == '{"a": 1}'
