from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.models import Language, TranslationRequest, TranslationResponse
from app.providers import MockTranslator, TranslationError, Translator

LANGUAGES = [
    Language(code="ar", name="Arabic"),
    Language(code="de", name="German"),
    Language(code="en", name="English"),
    Language(code="es", name="Spanish"),
    Language(code="fr", name="French"),
    Language(code="ja", name="Japanese"),
    Language(code="zh", name="Chinese"),
]


def create_app(translator: Translator | None = None) -> FastAPI:
    app = FastAPI(title="Realtime Translation API", version="0.1.0")
    active_translator = translator or MockTranslator()

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "name": "Realtime Translation API",
            "docs": "/docs",
            "health": "/api/health",
            "languages": "/api/languages",
            "translate": "/api/translate",
            "websocket": "/ws/translate",
        }

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/languages", response_model=list[Language])
    async def languages() -> list[Language]:
        return LANGUAGES

    @app.post("/api/translate", response_model=TranslationResponse)
    async def translate(request: TranslationRequest) -> TranslationResponse:
        try:
            return await active_translator.translate(request)
        except TranslationError as error:
            raise HTTPException(status_code=502, detail="Translation provider failed") from error

    @app.websocket("/ws/translate")
    async def translate_websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                try:
                    payload = await websocket.receive_json()
                    request_id = payload.get("request_id") if isinstance(payload, dict) else None
                    request = TranslationRequest.model_validate(payload)
                except ValidationError as error:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "request_id": request_id,
                            "error": "Invalid translation request",
                            "details": error.errors(include_input=False),
                        }
                    )
                    continue
                except ValueError:
                    await websocket.send_json(
                        {"type": "error", "error": "Expected a JSON translation request"}
                    )
                    continue

                try:
                    response = await active_translator.translate(request)
                except TranslationError:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "request_id": request_id,
                            "error": "Translation provider failed",
                        }
                    )
                    continue
                await websocket.send_json(
                    {
                        "type": "translation",
                        "request_id": request_id,
                        **response.model_dump(),
                    }
                )
        except WebSocketDisconnect:
            return

    return app


app = create_app()
