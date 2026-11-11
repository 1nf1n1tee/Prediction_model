# Realtime Translation API

A FastAPI backend with a REST endpoint, persistent WebSocket endpoint, and browser chat interface. Bangla is the chat's default target language. The default provider is the local M2M100 model, so translations are real rather than echoed.

M2M100 runs Meta's MIT-licensed multilingual model on your machine. It supports Bangla and the other listed languages without an API key. Model weights (about 1.8 GB) are downloaded from Hugging Face on the first translation request, not during server startup. Model inference runs on CPU by default and can be slow. The mock provider is available for UI testing; it echoes submitted text and marks results with `"provider": "mock"` and `"is_mock": true`.

For the technology stack, architecture, request flows, provider behavior, and project file tree, see [Project Documentation](docs/PROJECT_DOCUMENTATION.md).

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r model-requirements.txt
uvicorn app.main:app --reload
```

Open the root URL (`/`) for the translation chat interface. It connects to `/ws/translate` and loads language options from `/api/languages`. The interface shows whether a response came from the local model or the mock. Interactive API docs are available at `/docs`.

### Provider options

M2M100 is enabled by default. To explicitly select it or use another compatible Hugging Face model:

```powershell
$env:TRANSLATION_PROVIDER = "m2m100"
$env:TRANSLATION_MODEL = "facebook/m2m100_418M"
uvicorn app.main:app --reload
```

The default `facebook/m2m100_418M` supports English-to-Bangla and many other language pairs. M2M100 does not detect the source language: `"auto"` is treated as English, so select the actual source language for other input languages. The model accepts up to 1,024 input tokens; longer requests return an error instead of being silently truncated. To use the echo-only mock for UI testing, set `$env:TRANSLATION_PROVIDER = "mock"` before starting the server.

## HTTP API

- `GET /api/health` — service health
- `GET /api/languages` — available language codes
- `POST /api/translate` — translate one text; response includes `latency_ms`, the server-side provider execution time

Example request:

```json
{
  "text": "Hello",
  "source_language": "en",
  "target_language": "es"
}
```

The source language can be `"auto"`. Text must contain 1–5,000 characters; language codes use a two- or three-letter code, optionally followed by a two-letter region.

## WebSocket API

Connect to `/ws/translate` and send JSON translation requests using the same fields as the HTTP API. `request_id` is optional and is echoed in the response to correlate concurrent client messages. Successful responses include `latency_ms`, the server-side provider execution time; the chat displays this value below each translation.

Success response:

```json
{
  "type": "translation",
  "request_id": "request-1",
  "translated_text": "Hello",
  "source_language": "en",
  "target_language": "es",
  "provider": "mock",
  "is_mock": true
}
```

Invalid messages receive a `type: "error"` response; the connection remains open for later requests.

## Tests

```powershell
pytest
```
