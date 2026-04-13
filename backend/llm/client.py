from typing import Type, TypeVar
from pydantic import BaseModel

from config import settings
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langsmith import traceable

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def _get_openai_llm():
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set.")
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key,
    )


def _get_ollama_llm():
    return ChatOllama(
        model=settings.ollama_model,
        temperature=0,
    )


@traceable(run_type="llm", name="invoke_structured_with_fallback")
def invoke_structured_with_fallback(schema: Type[StructuredModel], prompt: str) -> StructuredModel:
    # Production: OpenAI only
    if settings.llm_provider == "openai":
        llm = _get_openai_llm().with_structured_output(schema)
        return llm.invoke(prompt)

    # Development fallback flow
    if settings.llm_provider == "openai_first":
        openai_error = None
        try:
            llm = _get_openai_llm().with_structured_output(schema)
            return llm.invoke(prompt)
        except Exception as e:
            openai_error = e
            print(f"[LLM] OpenAI failed, falling back to Ollama: {e}")

        try:
            llm = _get_ollama_llm().with_structured_output(schema)
            return llm.invoke(prompt)
        except Exception as ollama_error:
            raise RuntimeError(
                f"OpenAI failed: {openai_error}; Ollama failed: {ollama_error}"
            )

    # Optional local-only mode
    if settings.llm_provider == "ollama":
        llm = _get_ollama_llm().with_structured_output(schema)
        return llm.invoke(prompt)

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")