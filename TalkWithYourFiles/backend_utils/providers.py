import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel


"""
providers.py is the only module that knows about specific LLM providers (Anthropic, OpenRouter).
Everything else in the app asks this module for "a chat model" or "an embeddings model".

To add a new provider:
1) Add an entry to PROVIDERS below (the langchain provider name, env var names and a default model).
2) Install its langchain integration package (e.g. langchain-ollama) and add it to requirements.txt.
3) If it offers embeddings, add a branch to get_embeddings().

API keys:
- Keys are read from the environment / a .env file first (handy for local use & docker).
- Otherwise the user enters them in the sidebar. Those keys live only in the browser session
  and are passed explicitly to each client. They are never written to os.environ or to disk,
  so on a shared deployment one user's key can't leak into another user's session.
"""

load_dotenv()


@dataclass(frozen=True)
class Provider:
    label: str
    langchain_name: str            # name understood by langchain's init_chat_model
    env_vars: tuple                # env vars checked for the API key, in order
    default_model: str             # can be overridden with <PREFIX>_MODEL in .env, or in the GUI
    model_env_var: str
    default_embedding_model: Optional[str] = None   # None = provider has no embeddings API
    key_help_url: str = ""


PROVIDERS: Dict[str, Provider] = {
    "anthropic": Provider(
        label="Anthropic",
        langchain_name="anthropic",
        env_vars=("ANTHROPIC_API_KEY",),
        default_model="claude-opus-5-5",
        model_env_var="ANTHROPIC_MODEL",
        key_help_url="https://console.anthropic.com/settings/keys",
    ),
    "openrouter": Provider(
        label="OpenRouter",
        langchain_name="openrouter",
        env_vars=("OPENROUTER_API_KEY",),
        # OpenRouter's auto router picks a suitable model per prompt. Any model id from
        # https://openrouter.ai/models works too, e.g. "anthropic/claude-sonnet-5-5".
        default_model="openrouter/auto",
        model_env_var="OPENROUTER_MODEL",
        default_embedding_model="openai/text-embedding-3-small",
        key_help_url="https://openrouter.ai/keys",
    ),
}

# Used when no embeddings-capable key is available: plain keyword (BM25) retrieval.
KEYWORD_RETRIEVAL = "keyword"


def env_api_key(provider_id: str) -> Optional[str]:
    """Returns the API key for the provider from the environment / .env, if there is one."""
    for var in PROVIDERS[provider_id].env_vars:
        value = os.getenv(var, "").strip()
        if value:
            return value
    return None


def default_model(provider_id: str) -> str:
    provider = PROVIDERS[provider_id]
    return os.getenv(provider.model_env_var, "").strip() or provider.default_model


def get_chat_model(provider_id: str, model_name: str, api_key: str, max_tokens: int) -> BaseChatModel:
    """Creates a chat model for the given provider. Sampling params are left at provider defaults,
    as some newer models reject a custom temperature."""
    return init_chat_model(
        model_name,
        model_provider=PROVIDERS[provider_id].langchain_name,
        api_key=api_key,
        max_tokens=max_tokens,
    )


class OpenRouterEmbeddings(Embeddings):
    """Embeddings through OpenRouter's embeddings endpoint (there's no LangChain integration for it yet)."""

    BATCH_SIZE = 100

    def __init__(self, model: str, api_key: str):
        import openrouter
        self.model = model
        self.client = openrouter.OpenRouter(api_key=api_key)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            response = self.client.embeddings.generate(
                input=texts[i:i + self.BATCH_SIZE], model=self.model, encoding_format="float")
            if isinstance(response, str):
                raise RuntimeError(f"Unexpected embeddings response: {response[:200]}")
            data = sorted(response.data, key=lambda d: d.index or 0)
            vectors.extend(list(d.embedding) for d in data)
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


def get_embeddings(provider_id: str, api_key: str) -> Embeddings:
    if provider_id == "openrouter":
        return OpenRouterEmbeddings(PROVIDERS["openrouter"].default_embedding_model, api_key)
    raise ValueError(f"{PROVIDERS[provider_id].label} doesn't provide an embeddings API.")


def pick_retrieval_provider(api_keys: Dict[str, str]) -> str:
    """Embeddings are needed for semantic search. Anthropic has no embeddings API,
    so we use OpenRouter embeddings when an OpenRouter key is available, else keyword search."""
    if api_keys.get("openrouter"):
        return "openrouter"
    return KEYWORD_RETRIEVAL


def validate_key(provider_id: str, api_key: str) -> bool:
    """Cheap check that a key works."""
    try:
        if provider_id == "anthropic":
            import anthropic
            anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=10).models.list(limit=1)
        elif provider_id == "openrouter":
            import openrouter
            openrouter.OpenRouter(api_key=api_key).api_keys.get_current_key_metadata(timeout_ms=10000)
        return True
    except Exception:
        return False
