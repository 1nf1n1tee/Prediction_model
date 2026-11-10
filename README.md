# Realtime Translation API

A FastAPI backend starter with a REST endpoint and a persistent WebSocket endpoint for translation requests. The default provider is a **mock**: it echoes the submitted text and marks the result with `"provider": "mock"` and `"is_mock": true`. Inject a real provider implementing `Translator` in `app/providers.py` and pass it to `create_app` when integrating a translation service. Provider adapters should raise `TranslationError` for upstream failures; REST returns HTTP 502 and WebSocket clients receive an error event while keeping the connection open.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The root URL (`/`) lists the available endpoints. Interactive API docs are available at `/docs`.

## HTTP API

- `GET /api/health` — service health
- `GET /api/languages` — available language codes
- `POST /api/translate` — translate one text

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

Connect to `/ws/translate` and send JSON translation requests using the same fields as the HTTP API. `request_id` is optional and is echoed in the response to correlate concurrent client messages.

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
