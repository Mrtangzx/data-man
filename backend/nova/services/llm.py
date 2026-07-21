from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..errors import NovaError


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    name: str
    base_url: str
    model: str
    api_key: str


PROVIDER_PRESETS: tuple[dict[str, str], ...] = (
    {"id": "openai", "name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    {"id": "kimi", "name": "Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "kimi-k2.6"},
    {"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    {
        "id": "qwen",
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    {"id": "custom", "name": "自定义供应商", "base_url": "", "model": ""},
)

_lock = RLock()
_runtime_providers: dict[str, ProviderConfig] = {}
_active_provider_id = "env"


def _env_provider() -> ProviderConfig:
    settings = get_settings()
    return ProviderConfig(
        id="env",
        name="环境变量配置",
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
    )


def _preset(provider_id: str) -> ProviderConfig | None:
    for item in PROVIDER_PRESETS:
        if item["id"] == provider_id:
            return ProviderConfig(**item, api_key="")
    return None


def get_active_provider_id() -> str:
    with _lock:
        return _active_provider_id


def get_provider(provider_id: str | None = None) -> ProviderConfig:
    selected_id = provider_id or get_active_provider_id()
    if selected_id == "env":
        with _lock:
            runtime_env = _runtime_providers.get("env")
        return runtime_env or _env_provider()
    with _lock:
        provider = _runtime_providers.get(selected_id)
    if provider:
        return provider
    preset = _preset(selected_id)
    if preset:
        return preset
    raise NovaError("NOVA-LLM-2604", "未找到所选模型供应商。", 404, details={"fix": "重新加载供应商列表。"})


def _public(provider: ProviderConfig) -> dict:
    return {
        "id": provider.id,
        "name": provider.name,
        "base_url": provider.base_url,
        "model": provider.model,
        "configured": bool(provider.api_key.strip() and provider.base_url.strip() and provider.model.strip()),
        "api_key_hint": "已配置" if provider.api_key.strip() else "未配置",
    }


def list_providers() -> dict:
    with _lock:
        saved = dict(_runtime_providers)
        active_id = _active_provider_id
    providers: list[dict] = []
    env = saved.get("env", _env_provider())
    providers.append(_public(env))
    for preset_data in PROVIDER_PRESETS:
        provider_id = preset_data["id"]
        providers.append(_public(saved.get(provider_id, _preset(provider_id))))
    for provider_id, provider in saved.items():
        if provider_id not in {item["id"] for item in PROVIDER_PRESETS}:
            providers.append(_public(provider))
    return {"providers": providers, "active_provider_id": active_id}


def save_provider(provider_id: str, name: str, base_url: str, model: str, api_key: str | None, active: bool) -> dict:
    base_url = base_url.strip().rstrip("/")
    model = model.strip()
    name = name.strip()
    parsed = urlparse(base_url)
    if not name or not model or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise NovaError(
            "NOVA-LLM-2601",
            "供应商名称、HTTPS 地址和模型名称均不能为空。",
            422,
            details={"fix": "检查供应商名称、Base URL 和模型名。"},
        )
    existing = get_provider(provider_id)
    next_key = existing.api_key if api_key is None else api_key.strip()
    provider = ProviderConfig(provider_id, name, base_url, model, next_key)
    with _lock:
        _runtime_providers[provider_id] = provider
        global _active_provider_id
        if active:
            _active_provider_id = provider_id
    return _public(provider)


def set_active_provider(provider_id: str) -> dict:
    provider = get_provider(provider_id)
    if not provider.api_key.strip():
        raise NovaError("NOVA-LLM-2602", "所选供应商尚未配置 API key。", 422, details={"fix": "先保存 API key。"})
    with _lock:
        global _active_provider_id
        _active_provider_id = provider_id
    return _public(provider)


def _http_call(endpoint: str, headers: dict[str, str], payload: dict) -> httpx.Response:
    with httpx.Client(timeout=get_settings().llm_timeout_seconds) as client:
        return client.post(endpoint, headers=headers, json=payload)


def chat_completion(provider: ProviderConfig, messages: list[dict[str, str]]) -> str:
    if not provider.api_key.strip():
        raise NovaError(
            "NOVA-LLM-2603",
            f"供应商“{provider.name}”尚未配置 API key。",
            503,
            details={"fix": "打开系统设置，填写 API key 后保存。"},
        )
    endpoint = f"{provider.base_url.rstrip('/')}/chat/completions"
    try:
        response = _http_call(
            endpoint,
            {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"},
            {"model": provider.model, "messages": messages},
        )
    except httpx.TimeoutException as error:
        raise NovaError("NOVA-RT-2503", "语言模型响应超时。", 504, retryable=True) from error
    except httpx.HTTPError as error:
        raise NovaError("NOVA-RT-2504", "无法连接语言模型服务。", 502, retryable=True) from error

    if response.status_code >= 400:
        retryable = response.status_code == 429 or response.status_code >= 500
        provider_message = ""
        provider_code = ""
        try:
            upstream_error = response.json().get("error", {})
            if isinstance(upstream_error, dict):
                provider_message = str(upstream_error.get("message") or "").strip()[:500]
                provider_code = str(upstream_error.get("code") or upstream_error.get("type") or "").strip()[:120]
        except (ValueError, AttributeError, TypeError):
            pass
        if provider.api_key and provider_message:
            provider_message = provider_message.replace(provider.api_key, "[redacted]")
        raise NovaError(
            "NOVA-RT-2502",
            f"语言模型请求被拒绝：{provider_message}" if provider_message else f"语言模型服务返回 HTTP {response.status_code}。",
            503 if retryable else 502,
            retryable=retryable,
            details={
                "fix": "检查 API key、模型名称、Base URL、请求参数和服务额度。",
                "provider_code": provider_code,
            },
        )
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise NovaError("NOVA-RT-2505", "语言模型返回了无法识别的响应。", 502) from error
    if not isinstance(content, str) or not content.strip():
        raise NovaError("NOVA-RT-2505", "语言模型返回了空回复。", 502)
    return content.strip()
