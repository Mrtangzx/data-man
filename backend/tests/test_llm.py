import httpx
import pytest

from nova.errors import NovaError
from nova.services import llm


def test_chat_completion_omits_cross_provider_temperature(monkeypatch):
    captured: dict = {}

    def fake_http_call(endpoint, headers, payload):
        captured.update({"endpoint": endpoint, "headers": headers, "payload": payload})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "连接成功"}}]},
            request=httpx.Request("POST", endpoint),
        )

    monkeypatch.setattr(llm, "_http_call", fake_http_call)
    provider = llm.ProviderConfig("kimi", "Kimi", "https://api.moonshot.cn/v1", "kimi-k2.6", "test-key")
    reply = llm.chat_completion(provider, [{"role": "user", "content": "你好"}])

    assert reply == "连接成功"
    assert captured["payload"] == {
        "model": "kimi-k2.6",
        "messages": [{"role": "user", "content": "你好"}],
    }


def test_chat_completion_surfaces_safe_provider_error(monkeypatch):
    def fake_http_call(endpoint, headers, payload):
        return httpx.Response(
            400,
            json={"error": {"type": "invalid_request_error", "message": "temperature must be 1.0"}},
            request=httpx.Request("POST", endpoint),
        )

    monkeypatch.setattr(llm, "_http_call", fake_http_call)
    provider = llm.ProviderConfig("kimi", "Kimi", "https://api.moonshot.cn/v1", "kimi-k2.6", "test-key")

    with pytest.raises(NovaError) as captured:
        llm.chat_completion(provider, [{"role": "user", "content": "你好"}])

    assert "temperature must be 1.0" in captured.value.message
    assert captured.value.details["provider_code"] == "invalid_request_error"
    assert "test-key" not in captured.value.message
