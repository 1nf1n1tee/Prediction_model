# Lingua — Project Documentation

## Overview

Lingua is a browser-based realtime translation app. Its FastAPI server delivers the chat interface, exposes HTTP endpoints, and handles translation requests over a persistent WebSocket connection. The default provider is Meta's local M2M100 model; the Bangla target is preselected in the interface. An echo-only mock provider is available for UI development and testing.

## Technology stack

| Area | Technology | Role |
|---|---|---|
| Language/runtime | Python 3.11+ | Backend implementation |
| Web/API | FastAPI, Uvicorn | HTTP routes, WebSocket handling, and ASGI server |
| Data validation | Pydantic | Validates translation requests and defines API responses |
| Frontend | HTML, CSS, vanilla JavaScript | Browser-based translation chat; no separate frontend build step |
| Realtime transport | WebSocket | Sends translation requests and receives correlated results |
| Translation | M2M100, Transformers, PyTorch, SentencePiece | Optional-dependency local multilingual translation model |
| Tests | pytest, FastAPI TestClient, HTTPX | API, WebSocket, provider, and static asset tests |

Core server/test dependencies are listed in `requirements.txt`. Model-specific dependencies are kept separately in `model-requirements.txt`, so the server can start without loading or installing the translation model.

## Architecture

```text
┌──────────────────────────── Browser ────────────────────────────┐
│                                                                  │
│  index.html ── styles.css                                        │
│      │                                                           │
│      └── app.js ── WebSocket /ws/translate ───────────────┐       │
│                   GET /api/languages                     │       │
└──────────────────────────────────────────────────────────│───────┘
                                                           │
┌──────────────────────────── FastAPI ─────────────────────│───────┐
│  Static assets and page ── GET /, /static/*              │       │
│  HTTP API ── health, languages, one-shot translation     │       │
│  WebSocket handler ── validate, translate, correlate ────┘       │
│                  │                                               │
│                  ▼                                               │
│       Translator protocol / configured provider                   │
│              ┌─────────────────┴────────────────┐                 │
│              ▼                                  ▼                 │
│     M2M100Translator                     MockTranslator           │
│     lazy model loading                   echoes input             │
│     PyTorch inference                    marks is_mock=true       │
└──────────────────────────────────────────────────────────────────┘
```

### Translation lifecycle

1. The browser opens `/` and loads its JavaScript and CSS from `/static/`.
2. The browser connects to `/ws/translate` and requests supported languages from `/api/languages`.
3. For each message, the browser sends text, source and target language codes, and a `request_id`.
4. FastAPI validates the payload using `TranslationRequest`.
5. `translate_timed` invokes the configured `Translator` and measures provider execution time with a monotonic timer.
6. The provider returns a `TranslationResponse`. FastAPI adds `latency_ms` and sends a response associated with the same `request_id`.
7. The browser displays the original text, translated text, provider/demo status, and server-side latency.

The HTTP endpoint `POST /api/translate` uses the same provider and latency measurement for one-shot requests.

### Provider behavior

- `M2M100Translator` is the default provider. Its model and tokenizer load lazily on the first translation request, not while Uvicorn starts. The model runs locally on CPU by default; the first request may download approximately 1.8 GB of model weights. A lock serializes model initialization and inference, and inference is moved off the async event loop.
- M2M100 supports many language pairs, including English and Bangla. `"auto"` is treated as English, not automatic language detection. Choose the actual source language for non-English input.
- Inputs exceeding the provider's 1,024-token limit are rejected rather than silently truncated.
- `MockTranslator` echoes the submitted text and identifies itself with `provider: "mock"` and `is_mock: true`. Select it by setting `TRANSLATION_PROVIDER=mock`.
- The provider is defined behind a `Translator` protocol, allowing another implementation to be added without changing the route contract.

### Error behavior

| Situation | HTTP endpoint | WebSocket |
|---|---|---|
| Invalid request | FastAPI validation response (422) | `type: "error"` with validation details |
| Input too long for model | 422 with explanation | `type: "error"` with explanation |
| Model dependencies/weights unavailable | 503 with setup guidance | `type: "error"` with setup guidance |
| Translation provider failure | 502 | `type: "error"`; connection remains open |

`GET /api/health` returns service health; it does not force the large local model to load.

## API summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Serve the chat interface |
| `GET` | `/static/{asset}` | Serve frontend assets |
| `GET` | `/favicon.ico` | Browser favicon fallback (204) |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/languages` | Supported language codes |
| `POST` | `/api/translate` | Translate a single request |
| `WS` | `/ws/translate` | Persistent realtime translation session |
| `GET` | `/docs` | FastAPI interactive API documentation |

Translation requests contain `text`, `target_language`, and optional `source_language` (default `"auto"`). Text length is limited to 5,000 characters at the API boundary.

Successful HTTP responses contain `translated_text`, `source_language`, `target_language`, `provider`, `is_mock`, and `latency_ms`. WebSocket success responses include the same fields plus `type: "translation"` and the echoed `request_id`. `latency_ms` measures server-side provider execution, not network round-trip time or browser rendering.

## Project file tree

```text
langFoyer/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, routes, WebSocket, latency
│   ├── models.py               # Pydantic request/response/language models
│   ├── providers.py            # Translator protocol, M2M100, mock, configuration
│   └── static/
│       ├── app.js              # WebSocket client and chat behavior
│       ├── favicon.svg         # Browser tab icon
│       ├── index.html          # Chat interface
│       └── styles.css          # Responsive page styling
├── docs/
│   └── PROJECT_DOCUMENTATION.md
├── tests/
│   └── test_api.py             # API, WebSocket, provider, and static tests
├── .gitignore
├── LICENSE
├── model-requirements.txt      # Optional PyTorch/Transformers dependencies
├── README.md                  # Quickstart and API usage
└── requirements.txt           # Core runtime and test dependencies
```

The virtual environment, Python caches, pytest cache, and downloaded Hugging Face model files are local generated files and are not part of the source tree.

## Setup and run (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r model-requirements.txt
uvicorn app.main:app --reload
```

Open the URL printed by Uvicorn, normally `http://127.0.0.1:8000/`. On the first translation, M2M100 may download its model weights.

To explicitly select a provider before starting the server:

```powershell
$env:TRANSLATION_PROVIDER = "m2m100"
$env:TRANSLATION_MODEL = "facebook/m2m100_418M"
uvicorn app.main:app --reload
```

For UI-only testing, set `$env:TRANSLATION_PROVIDER = "mock"`. Run the test suite with:

```powershell
pytest
```
