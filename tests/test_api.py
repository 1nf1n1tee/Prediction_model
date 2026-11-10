from fastapi.testclient import TestClient

from app.main import create_app
from app.models import TranslationRequest, TranslationResponse
from app.providers import TranslationError


class PrefixTranslator:
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(
            translated_text=f"{request.target_language}: {request.text}",
            source_language=request.source_language,
            target_language=request.target_language,
            provider="test",
            is_mock=False,
        )


class FailingTranslator:
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise TranslationError("Provider unavailable")


def test_health_and_languages() -> None:
    client = TestClient(create_app())

    assert client.get("/").json()["docs"] == "/docs"
    assert client.get("/api/health").json() == {"status": "ok"}
    assert {item["code"] for item in client.get("/api/languages").json()} >= {"en", "es"}


def test_translate_uses_injected_provider() -> None:
    client = TestClient(create_app(PrefixTranslator()))

    response = client.post(
        "/api/translate",
        json={"text": "Hello", "source_language": "en", "target_language": "es"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "translated_text": "es: Hello",
        "source_language": "en",
        "target_language": "es",
        "provider": "test",
        "is_mock": False,
    }


def test_translate_rejects_empty_text() -> None:
    client = TestClient(create_app())

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

    assert response == {
        "type": "translation",
        "request_id": "one",
        "translated_text": "es: Hello",
        "source_language": "en",
        "target_language": "es",
        "provider": "test",
        "is_mock": False,
    }


def test_websocket_reports_invalid_message_and_stays_open() -> None:
    client = TestClient(create_app())

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
