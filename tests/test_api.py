import asyncio
from contextlib import nullcontext
from threading import Lock
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import TranslationRequest, TranslationResponse
from app.providers import (
    M2M100Translator,
    MockTranslator,
    TranslationError,
    TranslationInputError,
    TranslationSetupError,
    configured_translator,
    model_language_code,
)


class PrefixTranslator:
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(
            translated_text=f"{request.target_language}: {request.text}",
            source_language=request.source_language,
            target_language=request.target_language,
            provider="test",
            is_mock=False,
        )


class SlowTranslator:
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        await asyncio.sleep(0.02)
        return TranslationResponse(
            translated_text=request.text,
            source_language=request.source_language,
            target_language=request.target_language,
            provider="slow-test",
            is_mock=False,
        )


class FailingTranslator:
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise TranslationError("Provider unavailable")


class SetupFailingTranslator:
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise TranslationSetupError(
            "Install the local model dependencies with 'pip install -r model-requirements.txt'."
        )


class FakeTokenizer:
    src_lang = ""
    input_length = 3

    def __call__(self, text: str, return_tensors: str) -> dict[str, object]:
        return {"input_ids": SimpleNamespace(shape=(1, self.input_length))}

    def get_lang_id(self, language: str) -> int:
        assert language == "bn"
        return 19

    def batch_decode(self, generated: list[str], skip_special_tokens: bool) -> list[str]:
        return ["হ্যালো"]


class FakeModel:
    def generate(self, **kwargs: object) -> list[str]:
        assert kwargs["forced_bos_token_id"] == 19
        assert kwargs["max_new_tokens"] == 1024
        return ["translated"]


def test_health_and_languages() -> None:
    client = TestClient(create_app(MockTranslator()))

    page = client.get("/")
    assert page.status_code == 200
    assert "Make every" in page.text
    assert 'value="bn" selected' in page.text
    assert 'href="/static/favicon.svg"' in page.text
    assert client.get("/favicon.ico").status_code == 204
    assert client.get("/static/favicon.svg").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok"}
    assert {item["code"] for item in client.get("/api/languages").json()} >= {
        "bn",
        "en",
        "es",
    }


def test_model_language_code_uses_english_for_auto_and_strips_region() -> None:
    assert model_language_code("auto") == "en"
    assert model_language_code("bn-BD") == "bn"


def test_m2m100_provider_defers_model_loading_until_translation(monkeypatch) -> None:
    monkeypatch.delenv("TRANSLATION_PROVIDER", raising=False)

    translator = configured_translator()

    assert isinstance(translator, M2M100Translator)
    assert translator._torch is None
    assert translator._model is None


def test_mock_provider_can_be_selected_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_PROVIDER", "mock")

    translator = configured_translator()

    assert isinstance(translator, MockTranslator)


def test_m2m100_provider_defers_model_loading_when_selected(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_PROVIDER", "m2m100")

    translator = configured_translator()

    assert isinstance(translator, M2M100Translator)
    assert translator._torch is None
    assert translator._tokenizer is None
    assert translator._model is None


def test_m2m100_translates_to_bangla_without_downloading_model() -> None:
    translator = M2M100Translator.__new__(M2M100Translator)
    translator._torch = SimpleNamespace(inference_mode=nullcontext)
    translator._tokenizer = FakeTokenizer()
    translator._model = FakeModel()
    translator._model_name = "facebook/m2m100_418M"
    translator._inference_lock = Lock()

    response = asyncio.run(
        translator.translate(
            TranslationRequest(text="Hello", target_language="bn")
        )
    )

    assert response.translated_text == "হ্যালো"
    assert response.source_language == "en"
    assert response.target_language == "bn"
    assert response.is_mock is False
    assert translator._tokenizer.src_lang == "en"


def test_m2m100_rejects_input_over_model_limit() -> None:
    translator = M2M100Translator.__new__(M2M100Translator)
    translator._torch = SimpleNamespace(inference_mode=nullcontext)
    translator._tokenizer = FakeTokenizer()
    translator._tokenizer.input_length = 1025
    translator._model = FakeModel()
    translator._model_name = "facebook/m2m100_418M"
    translator._inference_lock = Lock()

    with pytest.raises(TranslationInputError, match="too long"):
        asyncio.run(
            translator.translate(
                TranslationRequest(text="Hello", target_language="bn")
            )
        )


def test_translate_uses_injected_provider() -> None:
    client = TestClient(create_app(PrefixTranslator()))

    response = client.post(
        "/api/translate",
        json={"text": "Hello", "source_language": "en", "target_language": "es"},
    )

    assert response.status_code == 200
    result = response.json()
    assert {key: value for key, value in result.items() if key != "latency_ms"} == {
        "translated_text": "es: Hello",
        "source_language": "en",
        "target_language": "es",
        "provider": "test",
        "is_mock": False,
    }
    assert isinstance(result["latency_ms"], (int, float))
    assert result["latency_ms"] >= 0


def test_translate_reports_elapsed_provider_latency() -> None:
    client = TestClient(create_app(SlowTranslator()))

    response = client.post(
        "/api/translate",
        json={"text": "Hello", "source_language": "en", "target_language": "bn"},
    )

    assert response.status_code == 200
    assert response.json()["latency_ms"] >= 10


def test_translate_rejects_empty_text() -> None:
    client = TestClient(create_app(MockTranslator()))

    response = client.post(
        "/api/translate",
        json={"text": "", "target_language": "es"},
    )

    assert response.status_code == 422


def test_translate_surfaces_provider_failure() -> None:
    client = TestClient(create_app(FailingTranslator()))

    response = client.post(
        "/api/translate",
        json={"text": "Hello", "target_language": "es"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Translation provider failed"}


def test_translate_explains_missing_model_setup() -> None:
    client = TestClient(create_app(SetupFailingTranslator()))

    response = client.post(
        "/api/translate",
        json={"text": "Hello", "target_language": "bn"},
    )

    assert response.status_code == 503
    assert "pip install -r model-requirements.txt" in response.json()["detail"]


def test_websocket_translates_multiple_messages() -> None:
    client = TestClient(create_app(PrefixTranslator()))

    with client.websocket_connect("/ws/translate") as websocket:
        websocket.send_json(
            {
                "request_id": "one",
                "text": "Hello",
                "source_language": "en",
                "target_language": "es",
            }
        )
        response = websocket.receive_json()

    assert {key: value for key, value in response.items() if key != "latency_ms"} == {
        "type": "translation",
        "request_id": "one",
        "translated_text": "es: Hello",
        "source_language": "en",
        "target_language": "es",
        "provider": "test",
        "is_mock": False,
    }
    assert isinstance(response["latency_ms"], (int, float))
    assert response["latency_ms"] >= 0


def test_websocket_reports_invalid_message_and_stays_open() -> None:
    client = TestClient(create_app(MockTranslator()))

    with client.websocket_connect("/ws/translate") as websocket:
        websocket.send_json({"request_id": "bad", "text": "", "target_language": "es"})
        response = websocket.receive_json()
        websocket.send_json({"text": "Hello", "target_language": "es"})
        next_response = websocket.receive_json()

    assert response["type"] == "error"
    assert response["request_id"] == "bad"
    assert response["error"] == "Invalid translation request"
    assert next_response["type"] == "translation"
    assert next_response["is_mock"] is True


def test_websocket_keeps_connection_open_after_provider_failure() -> None:
    client = TestClient(create_app(FailingTranslator()))

    with client.websocket_connect("/ws/translate") as websocket:
        websocket.send_json(
            {"request_id": "failed", "text": "Hello", "target_language": "es"}
        )
        error = websocket.receive_json()
        websocket.send_json(
            {"request_id": "next", "text": "Hello", "target_language": "fr"}
        )
        next_error = websocket.receive_json()

    assert error == {
        "type": "error",
        "request_id": "failed",
        "error": "Translation provider failed",
    }
    assert next_error["request_id"] == "next"
