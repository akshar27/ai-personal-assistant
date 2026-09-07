"""Text embeddings for retrieval.

Mirrors `llm/client.py`: OpenAI by default, optional Ollama fallback in
development, and a clear error if neither is reachable. Callers get plain
`list[float]` vectors and never see the provider.
"""

import logging
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from config import settings

logger = logging.getLogger("ai_assistant.embeddings")

# text-embedding-3-small -> 1536 dims. Kept in one place so the store can assert.
EMBEDDING_DIM = 1536


@lru_cache(maxsize=1)
def _openai_embedder() -> OpenAIEmbeddings:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set.")
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )


@lru_cache(maxsize=1)
def _ollama_embedder():
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError as e:
        raise RuntimeError(
            "Ollama embedding fallback requested but langchain-ollama is not "
            "installed. Install it or set LLM_PROVIDER=openai."
        ) from e
    return OllamaEmbeddings(model=settings.ollama_embedding_model)


def _embedder():
    if settings.llm_provider == "ollama":
        return _ollama_embedder()
    try:
        return _openai_embedder()
    except Exception:
        if settings.llm_provider == "openai_first":
            logger.warning("OpenAI embeddings unavailable; falling back to Ollama")
            return _ollama_embedder()
        raise


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents. Order is preserved."""
    if not texts:
        return []
    return _embedder().embed_documents(list(texts))


def embed_query(text: str) -> list[float]:
    """Embed a single search query."""
    return _embedder().embed_query(text)
