from suwinvtools_server.signals.setup import WEBHOOK, model_names, set_keys


def test_set_keys_replaces_in_place_and_appends_the_rest() -> None:
    text = "# comment\nPORT=6240\n# LLM_MODEL=example\nLLM_BASE_URL=old\n"

    result = set_keys(text, {"LLM_BASE_URL": "http://new/v1", "LLM_MODEL": "qwen", "DISCORD_WEBHOOK_RED": "https://x"})

    assert result == "# comment\nPORT=6240\nLLM_MODEL=qwen\nLLM_BASE_URL=http://new/v1\nDISCORD_WEBHOOK_RED=https://x\n"


def test_only_discord_webhooks_pass() -> None:
    assert WEBHOOK.match("https://discord.com/api/webhooks/123456/abc-DEF_9")
    assert WEBHOOK.match("https://canary.discord.com/api/webhooks/1/x")
    assert not WEBHOOK.match("https://evil.example/api/webhooks/1/x")
    assert not WEBHOOK.match("https://discord.com/api/webhooks/1/x?wait=true")


def test_model_names_of_an_openai_models_answer() -> None:
    assert model_names(b'{"object": "list", "data": [{"id": "qwen38"}, {"id": "llama"}]}') == ["qwen38", "llama"]
