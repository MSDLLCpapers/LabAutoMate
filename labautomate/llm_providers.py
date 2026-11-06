"""
llm_providers.py
Unified multi-provider LLM interface for LabAutoMate.

Supports OpenAI and Anthropic Claude through their official SDKs. Requests go to each
provider's public API by default; a different Endpoint URL (for example a compatible
proxy) is passed to the SDK as its base URL.
"""

import json
import re
from dataclasses import dataclass
from typing import Optional, Generator

import openai
import anthropic


# ─────────────────────────────────────────────────────────────────────
# Provider configurations
# ─────────────────────────────────────────────────────────────────────

PROVIDERS = {
    "OpenAI": {
        "models": [
            "gpt-4.1-2025-04-14",
            "gpt-4.1-mini-2025-04-14",
            "gpt-4o-2024-11-20",
            "gpt-4o-mini-2024-07-18",
        ],
        "default_model": "gpt-4.1-2025-04-14",
        "default_endpoint": "https://api.openai.com/v1",
    },
    "Anthropic": {
        "models": [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20251001",
        ],
        "default_model": "claude-sonnet-4-6",
        "default_endpoint": "https://api.anthropic.com",
    },
}

DEFAULT_ENDPOINT = PROVIDERS["OpenAI"]["default_endpoint"]

# Sidebar help texts (kept here so app.py is the same on every branch).
API_KEY_HELP = "Your OpenAI or Anthropic API key."
ENDPOINT_HELP = (
    "API base URL. Defaults: https://api.openai.com/v1 (OpenAI) or "
    "https://api.anthropic.com (Anthropic). If the URL does not match the "
    "selected provider, the provider's public URL is used."
)
MODEL_IMPORT_PLACEHOLDER = "e.g. gpt-4.1-nano-2025-04-14, gpt-4.1-2025-04-14"


@dataclass
class LLMConfig:
    """Configuration for an LLM call."""
    provider: str
    model: str
    api_key: str
    endpoint: str = DEFAULT_ENDPOINT
    timeout: int = 600


def _openai_base_url(endpoint: str) -> str:
    """Base URL for the OpenAI SDK (includes /v1)."""
    endpoint = (endpoint or "").strip().rstrip("/")
    if not endpoint or "api.anthropic.com" in endpoint:
        # Empty, or the Anthropic URL left over after switching provider.
        return PROVIDERS["OpenAI"]["default_endpoint"]
    return endpoint


def _anthropic_base_url(endpoint: str) -> str:
    """Base URL for the Anthropic SDK (no /v1; the SDK appends /v1/messages)."""
    endpoint = (endpoint or "").strip().rstrip("/")
    if not endpoint or "api.openai.com" in endpoint:
        # Empty, or the OpenAI URL left over after switching provider.
        return PROVIDERS["Anthropic"]["default_endpoint"]
    if endpoint.endswith("/v1"):
        endpoint = endpoint[: -len("/v1")]
    return endpoint


# ─────────────────────────────────────────────────────────────────────
# Unified completion interface
# ─────────────────────────────────────────────────────────────────────

def complete(config: LLMConfig, prompt: str, system_prompt: str = "") -> str:
    if config.provider == "Anthropic":
        return _complete_anthropic(config, prompt, system_prompt)
    else:
        return _complete_openai(config, prompt, system_prompt)


def stream(config: LLMConfig, prompt: str, system_prompt: str = "") -> Generator[str, None, None]:
    if config.provider == "Anthropic":
        yield from _stream_anthropic(config, prompt, system_prompt)
    else:
        yield from _stream_openai(config, prompt, system_prompt)


# ─────────────────────────────────────────────────────────────────────
# OpenAI (Chat Completions)
# ─────────────────────────────────────────────────────────────────────

def _build_openai_client(config: LLMConfig):
    return openai.OpenAI(
        api_key=config.api_key,
        base_url=_openai_base_url(config.endpoint),
        timeout=config.timeout,
    )


def _complete_openai(config: LLMConfig, prompt: str, system_prompt: str) -> str:
    client = _build_openai_client(config)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=config.model,
        messages=messages,
    )
    return response.choices[0].message.content


def _stream_openai(config: LLMConfig, prompt: str, system_prompt: str) -> Generator[str, None, None]:
    client = _build_openai_client(config)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response_stream = client.chat.completions.create(
        model=config.model,
        messages=messages,
        stream=True,
    )
    for chunk in response_stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ─────────────────────────────────────────────────────────────────────
# Anthropic Claude (Messages API)
# ─────────────────────────────────────────────────────────────────────

def _build_anthropic_client(config: LLMConfig) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=config.api_key,
        base_url=_anthropic_base_url(config.endpoint),
        timeout=config.timeout,
    )


def _anthropic_kwargs(config: LLMConfig, prompt: str, system_prompt: str) -> dict:
    kwargs = {
        "model": config.model,
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    return kwargs


def _complete_anthropic(config: LLMConfig, prompt: str, system_prompt: str) -> str:
    client = _build_anthropic_client(config)
    response = client.messages.create(**_anthropic_kwargs(config, prompt, system_prompt))
    # Join the text blocks; models that think return a thinking block first.
    return "".join(b.text for b in response.content if b.type == "text")


def _stream_anthropic(config: LLMConfig, prompt: str, system_prompt: str) -> Generator[str, None, None]:
    client = _build_anthropic_client(config)
    with client.messages.stream(**_anthropic_kwargs(config, prompt, system_prompt)) as s:
        for text in s.text_stream:
            yield text


# ─────────────────────────────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────────────────────────────

def get_provider_names() -> list:
    return list(PROVIDERS.keys())


def get_models_for_provider(provider: str) -> list:
    return PROVIDERS.get(provider, {}).get("models", [])


def get_default_model(provider: str) -> str:
    return PROVIDERS.get(provider, {}).get("default_model", "")


def get_default_endpoint(provider: str) -> str:
    return PROVIDERS.get(provider, {}).get("default_endpoint", DEFAULT_ENDPOINT)


# ─────────────────────────────────────────────────────────────────────
# User-imported models (for ids that are not in the built-in dropdown)
# ─────────────────────────────────────────────────────────────────────

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")


def _collect_model_ids(obj) -> list:
    """Pull model id strings out of parsed JSON.

    Handles a bare string, a list of strings or objects, an object with an id/model/name
    field, and wrapper objects such as {"models": [...]} or the {"data": [...]} body
    returned by GET /v1/models.
    """
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, list):
        ids = []
        for item in obj:
            ids.extend(_collect_model_ids(item))
        return ids
    if isinstance(obj, dict):
        for key in ("data", "models"):
            if key in obj:
                return _collect_model_ids(obj[key])
        for key in ("id", "model", "name"):
            if isinstance(obj.get(key), str):
                return [obj[key]]
    return []


def parse_model_import(text: str) -> tuple:
    """Parse user-supplied model info into (valid_ids, rejected_entries).

    Accepts model ids separated by commas, semicolons, spaces or new lines, or JSON in
    any of the shapes handled by _collect_model_ids. Duplicates are dropped; entries that
    are not plausible model ids are returned in rejected_entries.
    """
    text = (text or "").strip()
    if not text:
        return [], []

    candidates = None
    if text[0] in "[{":
        try:
            candidates = _collect_model_ids(json.loads(text))
        except ValueError:
            candidates = None
    if candidates is None:
        candidates = [t.strip("\"'") for t in re.split(r"[,;\s]+", text)]

    valid, rejected = [], []
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        if _MODEL_ID_RE.match(candidate):
            if candidate not in valid:
                valid.append(candidate)
        elif candidate not in rejected:
            rejected.append(candidate)
    return valid, rejected


def merge_models(builtin: list, extra: list) -> list:
    """Built-in models first, then imported ones, without duplicates."""
    return list(builtin) + [m for m in extra if m not in builtin]


def validate_config(config: LLMConfig) -> Optional[str]:
    if not config.api_key or not config.api_key.strip():
        return "API key is required."
    if not config.endpoint or not config.endpoint.strip():
        return "Endpoint URL is required."
    if config.provider not in PROVIDERS:
        return f"Unknown provider: {config.provider}"
    if not config.model:
        return "Model selection is required."
    return None
