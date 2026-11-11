from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.models import Language, TranslationRequest, TranslationResponse
from app.providers import (
    TranslationError,
    TranslationInputError,
    TranslationSetupError,
    Translator,
    configured_translator,
)

STATIC_DIR = Path(__file__).parent / "static"

LANGUAGES = [
    Language(code="ar", name="Arabic"),
    Language(code="bn", name="Bangla"),
    Language(code="de", name="German"),
    Language(code="en", name="English"),
    Language(code="es", name="Spanish"),
    Language(code="fr", name="French"),
    Language(code="ja", name="Japanese"),
    Language(code="zh", name="Chinese"),
]


def create_app(translator: Translator | None = None) -> FastAPI:
    app = FastAPI(title="Realtime Translation API", version="0.1.0")
    active_translator = translator if translator is not None else configured_translator()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/languages", response_model=list[Language])
    async def languages() -> list[Language]:
        return LANGUAGES

    @app.post("/api/translate", response_model=TranslationResponse)
    async def translate(request: TranslationRequest) -> TranslationResponse:
        try:
            return await translate_timed(active_translator, request)
        except TranslationInputError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except TranslationSetupError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
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
                    response = await translate_timed(active_translator, request)
                except TranslationInputError as error:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "request_id": request_id,
                            "error": str(error),
                        }
                    )
                    continue
                except TranslationSetupError as error:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "request_id": request_id,
                            "error": str(error),
                        }
                    )
                    continue
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


async def translate_timed(
    translator: Translator,
    request: TranslationRequest,
) -> TranslationResponse:
    started_at = perf_counter()
    response = await translator.translate(request)
    latency_ms = round((perf_counter() - started_at) * 1000, 2)
    return response.model_copy(update={"latency_ms": latency_ms})


app = create_app()
