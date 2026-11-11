const connection = document.querySelector(".connection");
const connectionLabel = document.querySelector("#connection-label");
const sourceLanguage = document.querySelector("#source-language");
const targetLanguage = document.querySelector("#target-language");
const providerBadge = document.querySelector("#provider-badge");
const conversation = document.querySelector("#conversation");
const emptyState = document.querySelector("#empty-state");
const notice = document.querySelector("#notice");
const composer = document.querySelector("#composer");
const messageInput = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const pendingMessages = new Map();

let socket;
let requestSequence = 0;
let reconnectTimer;

function setConnectionState(state, label) {
  connection.classList.toggle("is-connected", state === "connected");
  connection.classList.toggle("is-disconnected", state === "disconnected");
  connectionLabel.textContent = label;
}

function showNotice(message, isError = false) {
  notice.hidden = !message;
  notice.textContent = message;
  notice.classList.toggle("is-error", isError);
}

function connect() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  setConnectionState("connecting", "Connecting");
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${protocol}//${window.location.host}/ws/translate`);

  socket.addEventListener("open", () => {
    clearTimeout(reconnectTimer);
    setConnectionState("connected", "Connected");
    showNotice("");
  });

  socket.addEventListener("message", (event) => {
    let response;
    try {
      response = JSON.parse(event.data);
    } catch {
      showNotice("Received an unreadable response from the server.", true);
      return;
    }

    const pending = pendingMessages.get(response.request_id);
    if (!pending) {
      showNotice(response.error || "The server could not process that message.", true);
      return;
    }

    pendingMessages.delete(response.request_id);
    pending.container.classList.remove("is-pending");
    if (response.type === "error") {
      pending.container.classList.add("has-error");
      pending.content.textContent = response.error || "Translation failed.";
      return;
    }

    pending.content.textContent = response.translated_text;
    pending.language.textContent = response.target_language.toUpperCase();
    if (response.is_mock) {
      pending.mockTag.hidden = false;
      providerBadge.lastChild.textContent = " MOCK DEMO";
    } else {
      providerBadge.lastChild.textContent = " LIVE TRANSLATION";
    }
    if (Number.isFinite(response.latency_ms) && response.latency_ms >= 0) {
      pending.latency.textContent = formatLatency(response.latency_ms);
      pending.latency.hidden = false;
      pending.latency.title = "Time spent translating on the server";
    }
    conversation.scrollTop = conversation.scrollHeight;
  });

  socket.addEventListener("close", () => {
    setConnectionState("disconnected", "Reconnecting");
    for (const [requestId, pending] of pendingMessages) {
      pendingMessages.delete(requestId);
      pending.container.classList.remove("is-pending");
      pending.container.classList.add("has-error");
      pending.content.textContent = "Connection lost. Please send your message again.";
    }
    reconnectTimer = window.setTimeout(connect, 2000);
  });

  socket.addEventListener("error", () => {
    setConnectionState("disconnected", "Connection issue");
  });
}

function appendMessage(text, requestId) {
  emptyState.hidden = true;

  const original = document.createElement("article");
  original.className = "message";
  const originalLabel = document.createElement("div");
  originalLabel.className = "message-label";
  originalLabel.textContent = "YOU";
  const originalText = document.createElement("div");
  originalText.className = "message-original";
  originalText.textContent = text;
  original.append(originalLabel, originalText);

  const translation = document.createElement("article");
  translation.className = "translation is-pending";
  const translatedText = document.createElement("div");
  translatedText.className = "translation-content";
  translatedText.textContent = "Translating...";
  const meta = document.createElement("div");
  meta.className = "translation-meta";
  const language = document.createElement("span");
  language.textContent = targetLanguage.value.toUpperCase();
  const mockTag = document.createElement("span");
  mockTag.className = "mock-tag";
  mockTag.textContent = "DEMO";
  mockTag.hidden = true;
  const latency = document.createElement("span");
  latency.className = "latency";
  latency.hidden = true;
  meta.append(language, mockTag, latency);
  translation.append(translatedText, meta);

  conversation.append(original, translation);
  conversation.scrollTop = conversation.scrollHeight;
  pendingMessages.set(requestId, {
    container: translation,
    content: translatedText,
    language,
    mockTag,
    latency,
  });
}

function formatLatency(milliseconds) {
  if (milliseconds < 1000) {
    return milliseconds < 1 ? "<1 ms" : `${Math.round(milliseconds)} ms`;
  }
  return `${(milliseconds / 1000).toFixed(2)} s`;
}

async function loadLanguages() {
  try {
    const response = await fetch("/api/languages");
    if (!response.ok) {
      throw new Error(`Language list request failed (${response.status}).`);
    }
    const languages = await response.json();
    const currentSource = sourceLanguage.value;
    const currentTarget = targetLanguage.value;

    sourceLanguage.replaceChildren(new Option("Detect language", "auto"));
    targetLanguage.replaceChildren();
    for (const language of languages) {
      sourceLanguage.add(new Option(language.name, language.code));
      targetLanguage.add(new Option(language.name, language.code));
    }
    sourceLanguage.value = currentSource;
    targetLanguage.value = currentTarget;
  } catch {
    showNotice("Could not load the language list. The default language choices are available.", true);
  }
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text) {
    return;
  }
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    showNotice("The translation service is reconnecting. Please try again in a moment.", true);
    return;
  }

  requestSequence += 1;
  const requestId = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID()
    : `${Date.now()}-${requestSequence}`;
  appendMessage(text, requestId);
  showNotice("");

  try {
    socket.send(JSON.stringify({
      request_id: requestId,
      text,
      source_language: sourceLanguage.value,
      target_language: targetLanguage.value,
    }));
    messageInput.value = "";
    messageInput.focus();
  } catch {
    const pending = pendingMessages.get(requestId);
    if (pending) {
      pending.container.classList.remove("is-pending");
      pending.container.classList.add("has-error");
      pending.content.textContent = "Could not send this message. Please try again.";
      pendingMessages.delete(requestId);
    }
  }
});

messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 120)}px`;
});

connect();
loadLanguages();
