"""Select the LLM adapter from settings. Add real providers here, behind the same interface."""

from app.core.config import Settings
from app.core.errors import AppError
from app.llm.base import LLMAdapter
from app.llm.mock import MockExtractiveAdapter


def create_llm_adapter(settings: Settings) -> LLMAdapter:
    provider = (settings.llm_provider or "mock").strip().lower()
    if provider == "mock":
        return MockExtractiveAdapter()
    raise AppError(
        503,
        "llm_not_configured",
        f"LLM provider '{provider}' is not supported. Set LLM_PROVIDER=mock or add an adapter.",
    )
