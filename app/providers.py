from typing import Protocol

from app.models import TranslationRequest, TranslationResponse


class TranslationError(Exception):
    """Raised when a translation provider cannot complete a request."""


class Translator(Protocol):
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Translate text and identify the provider used."""


class MockTranslator:
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(
            translated_text=request.text,
            source_language=request.source_language,
            target_language=request.target_language,
            provider="mock",
            is_mock=True,
        )
