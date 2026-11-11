import asyncio
import os
from threading import Lock
from typing import Any, Protocol

from app.models import TranslationRequest, TranslationResponse


class TranslationError(Exception):
    """Raised when a translation provider cannot complete a request."""


class TranslationInputError(TranslationError):
    """Raised when a request cannot be handled by the selected model."""


class TranslationSetupError(TranslationError):
    """Raised when a translation provider cannot be initialized."""


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


class M2M100Translator:
    def __init__(self, model_name: str = "facebook/m2m100_418M") -> None:
        self._model_name = model_name
        self._torch: Any = None
        self._tokenizer: Any = None
        self._model: Any = None
        self._inference_lock = Lock()

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        try:
            translated_text = await asyncio.to_thread(self._translate_sync, request)
        except TranslationError:
            raise
        except (IndexError, KeyError, OSError, RuntimeError, ValueError) as error:
            raise TranslationError("The local translation model failed") from error

        return TranslationResponse(
            translated_text=translated_text,
            source_language=model_language_code(request.source_language),
            target_language=request.target_language,
            provider=self._model_name,
            is_mock=False,
        )

    def _translate_sync(self, request: TranslationRequest) -> str:
        source_language = model_language_code(request.source_language)
        target_language = model_language_code(request.target_language)

        with self._inference_lock:
            if self._model is None:
                self._load_model()

            with self._torch.inference_mode():
                return self._translate_loaded(request)

    def _load_model(self) -> None:
        try:
            import torch
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        except ImportError as error:
            raise TranslationSetupError(
                "Install the local model dependencies with "
                "'pip install -r model-requirements.txt'."
            ) from error

        try:
            tokenizer = M2M100Tokenizer.from_pretrained(self._model_name)
            model = M2M100ForConditionalGeneration.from_pretrained(self._model_name)
        except (OSError, ValueError) as error:
            raise TranslationSetupError(
                f"Could not load {self._model_name}. Check your internet connection "
                "and available disk space, then try again."
            ) from error
        model.eval()
        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model

    def _translate_loaded(self, request: TranslationRequest) -> str:
        source_language = model_language_code(request.source_language)
        target_language = model_language_code(request.target_language)
        self._tokenizer.src_lang = source_language
        encoded = self._tokenizer(request.text, return_tensors="pt")
        if encoded["input_ids"].shape[-1] > 1024:
            raise TranslationInputError(
                "Text is too long for the local model; shorten it and try again."
            )
        generated = self._model.generate(
            **encoded,
            forced_bos_token_id=self._tokenizer.get_lang_id(target_language),
            max_new_tokens=1024,
        )
        return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0]


def model_language_code(language: str) -> str:
    if language == "auto":
        return "en"
    return language.split("-", maxsplit=1)[0].lower()


def configured_translator() -> Translator:
    provider = os.getenv("TRANSLATION_PROVIDER", "m2m100").lower()
    if provider == "mock":
        return MockTranslator()
    if provider == "m2m100":
        return M2M100Translator(os.getenv("TRANSLATION_MODEL", "facebook/m2m100_418M"))
    raise RuntimeError(
        f"Unsupported TRANSLATION_PROVIDER {provider!r}; use 'm2m100' or 'mock'."
    )
