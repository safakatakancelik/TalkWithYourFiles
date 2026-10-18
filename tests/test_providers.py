"""
Runs the real provider integrations (langchain-anthropic, langchain-openrouter and their SDKs) against
canned API responses, with only the HTTP transport faked. This checks that token usage is still parsed
correctly after dependency updates: CI runs these weekly with the newest allowed versions.
"""
import json

import httpx
import httpx2
import pytest

from backend_utils import providers
from backend_utils.qa_chain import run_qa_chain


ANTHROPIC_RESPONSE = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5-5",
    # Thinking models return a (possibly empty) thinking block before the text.
    "content": [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "Dogs bark."},
    ],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 1200, "output_tokens": 85,
              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
}

OPENROUTER_RESPONSE = {
    "id": "gen-test",
    "object": "chat.completion",
    "created": 1760000000,
    "model": "openai/gpt-5-mini",
    "provider": "OpenAI",
    "system_fingerprint": None,
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": "Dogs bark."}}],
    # OpenRouter may send token counts as floats.
    "usage": {"prompt_tokens": 1200.0, "completion_tokens": 85.0, "total_tokens": 1285.0,
              "completion_tokens_details": {"reasoning_tokens": 40}, "cost": 0.0012},
}

OPENROUTER_EMBEDDINGS_RESPONSE = {
    "object": "list",
    "model": "openai/text-embedding-3-small",
    "data": [
        {"object": "embedding", "index": 1, "embedding": [0.0, 1.0]},
        {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
    ],
}


@pytest.fixture
def fake_http(monkeypatch):
    """Answers every HTTP request with the canned body registered for its URL path; records the requests."""
    routes, requests = {}, []

    def handler(response_cls):
        def handle_request(self, request):
            requests.append(request)
            body = next(body for path, body in routes.items() if request.url.path.endswith(path))
            return response_cls(200, json=body, headers={"content-type": "application/json"}, request=request)
        return handle_request

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handler(httpx.Response))     # openrouter SDK
    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", handler(httpx2.Response))   # anthropic SDK
    return routes, requests


@pytest.mark.parametrize("provider_id, path, body", [
    ("anthropic", "/v1/messages", ANTHROPIC_RESPONSE),
    ("openrouter", "/chat/completions", OPENROUTER_RESPONSE),
])
def test_token_usage_is_parsed(fake_http, provider_id, path, body):
    routes, requests = fake_http
    routes[path] = body
    llm = providers.get_chat_model(provider_id, providers.default_model(provider_id), "test-key", max_tokens=4096)

    result = run_qa_chain(llm, ["some context " * 50], "What do dogs do?")

    assert result.answer == "Dogs bark."
    assert result.usage.reported
    assert result.usage.context_tokens + result.usage.question_tokens == 1200
    assert result.usage.context_tokens > result.usage.question_tokens
    assert result.usage.completion_tokens == 85
    assert result.usage.total == 1285

    sent = json.loads(requests[-1].content)
    assert sent["max_tokens"] == 4096
    assert sent["model"] == providers.default_model(provider_id)


def test_openrouter_embeddings(fake_http):
    routes, requests = fake_http
    routes["/embeddings"] = OPENROUTER_EMBEDDINGS_RESPONSE
    embeddings = providers.get_embeddings("openrouter", "test-key")

    assert embeddings.embed_documents(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]  # sorted by index
    assert json.loads(requests[-1].content)["model"] == "openai/text-embedding-3-small"
