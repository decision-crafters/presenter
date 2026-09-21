"""LLM provider factory.

One place to construct the LLM so the rest of the app only ever sees the
abstract ``llama_index.core.llms.llm.LLM`` interface. Supported providers:

- ``ollama``       — local Ollama daemon (default), e.g. http://localhost:11434
- ``ollama-cloud`` — Ollama Cloud, via its OpenAI-compatible endpoint + API key
- ``openai``       — OpenAI (kept as a switchable option)

Selection comes from ``--provider``/``--model`` on the CLI, falling back to the
``LLM_PROVIDER``/``LLM_MODEL`` env vars, then to the defaults below.
"""

import os
from typing import Optional

from llama_index.core.llms.llm import LLM

DEFAULT_PROVIDER = "ollama"
DEFAULT_MODELS = {
    "ollama": "qwen2.5:7b",
    "ollama-cloud": "qwen2.5:7b",
    "openai": "gpt-4o-mini",
}

# Local Ollama models can be slow to cold-start or generate structured output;
# the llama-index default request_timeout of 30s reliably times out.
OLLAMA_REQUEST_TIMEOUT = 300.0
OLLAMA_CONTEXT_WINDOW = 8000

# Ollama Cloud exposes an OpenAI-compatible API; we reach it through OpenAILike
# so the bearer token is handled cleanly as an api_key.
OLLAMA_CLOUD_BASE_URL = "https://ollama.com/v1"


def resolve_provider(provider: Optional[str]) -> str:
    return (provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()


def resolve_model(provider: str, model: Optional[str]) -> str:
    return model or os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider, "")


def build_llm(provider: Optional[str] = None, model: Optional[str] = None) -> LLM:
    """Construct the LLM for the given provider.

    Imports are done lazily so a missing optional package only fails when that
    provider is actually selected.
    """
    provider = resolve_provider(provider)
    model = resolve_model(provider, model)

    if provider == "ollama":
        from llama_index.llms.ollama import Ollama

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return Ollama(
            model=model,
            base_url=base_url,
            request_timeout=OLLAMA_REQUEST_TIMEOUT,
            context_window=OLLAMA_CONTEXT_WINDOW,
        )

    if provider == "ollama-cloud":
        from llama_index.llms.openai_like import OpenAILike

        api_key = os.getenv("OLLAMA_CLOUD_API_KEY")
        if not api_key:
            raise ValueError(
                "OLLAMA_CLOUD_API_KEY is required for the 'ollama-cloud' provider."
            )
        base_url = os.getenv("OLLAMA_CLOUD_BASE_URL", OLLAMA_CLOUD_BASE_URL)
        # is_function_calling_model=True lets llama-index route structured_predict
        # through tool-calling instead of loose prompt-based JSON extraction.
        return OpenAILike(
            model=model,
            api_base=base_url,
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=True,
            context_window=OLLAMA_CONTEXT_WINDOW,
            timeout=OLLAMA_REQUEST_TIMEOUT,
        )

    if provider == "openai":
        from llama_index.llms.openai import OpenAI

        return OpenAI(model=model)

    raise ValueError(
        f"Unknown LLM provider: {provider!r}. "
        "Choose one of: ollama, ollama-cloud, openai."
    )
