import { defineStore } from "pinia";
import { ref } from "vue";

/**
 * Chat store — mirrors the webchat gateway protocol.
 *
 * Key differences from the old HTTP/SSE approach:
 * - Server (gateway) keeps the full conversation history per sessionKey.
 * - We only send the message text, not the full history.
 * - Streaming arrives as `chat` events (delta / final / aborted / error).
 * - `loadHistory` fetches persisted messages from the server.
 */

export interface ChatMessage {
  role: string;
  content: unknown; // string or content-block array
  timestamp?: number;
  text?: string;
}

export const useChatStore = defineStore("chat", () => {
  // ── State ──
  const sessionKey = ref("default");
  /** The resolved session key returned by the gateway (may differ from what we send). */
  const resolvedSessionKey = ref<string | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const loading = ref(false);
  const sending = ref(false);
  const streaming = ref(false);
  const streamText = ref("");
  const streamStartedAt = ref<number | null>(null);
  const chatRunId = ref<string | null>(null);
  const lastError = ref<string | null>(null);
  const wsConnected = ref(false);

  /** Per-agent last message preview text */
  const lastMessageMap = ref<Record<string, string>>({});

  // ── Helpers ──

  function extractText(message: unknown): string | null {
    const m = message as Record<string, unknown>;
    if (typeof m.content === "string") return m.content;
    if (typeof m.text === "string") return m.text;
    if (Array.isArray(m.content)) {
      return (m.content as Array<Record<string, unknown>>)
        .filter((p) => p.type === "text" && typeof p.text === "string")
        .map((p) => p.text as string)
        .join("");
    }
    return null;
  }

  // ── Actions ──

  /** Switch to a different session. */
  async function switchSession(key: string) {
    sessionKey.value = key;
    await loadHistory();
  }

  /** Fetch history from the gateway for the current session. */
  async function loadHistory() {
    loading.value = true;
    lastError.value = null;
    try {
      const key = resolvedSessionKey.value || sessionKey.value;
      const res = await window.openclaw.chat.loadHistory(key);
      const raw = Array.isArray(res.messages) ? res.messages : [];
      messages.value = raw as ChatMessage[];
      // Update last message preview for this session
      _updateLastPreview();
      // Clear streaming state — history includes finalized messages
      streamText.value = "";
      streaming.value = false;
      chatRunId.value = null;
      streamStartedAt.value = null;
    } catch (err) {
      lastError.value = String(err);
    } finally {
      loading.value = false;
    }
  }

  /** Send a message to the current session. */
  async function sendMessage(text: string) {
    const msg = text.trim();
    if (!msg) return;

    // Optimistic: add user message locally
    messages.value = [
      ...messages.value,
      { role: "user", content: [{ type: "text", text: msg }], timestamp: Date.now() },
    ];
    _updateLastPreview();

    sending.value = true;
    lastError.value = null;
    streamText.value = "";
    streamStartedAt.value = Date.now();
    streaming.value = true;

    try {
      await window.openclaw.chat.sendMessage(sessionKey.value, msg);
    } catch (err) {
      const error = String(err);
      lastError.value = error;
      streaming.value = false;
      sending.value = false;
      messages.value = [
        ...messages.value,
        { role: "assistant", content: [{ type: "text", text: "Error: " + error }], timestamp: Date.now() },
      ];
      return;
    }
    sending.value = false;
  }

  /** Handle an incoming chat event from the gateway. */
  function handleChatEvent(payload: ChatEventPayload) {
    // The gateway normalizes session keys (e.g. "default" → "agent:main:default").
    // Accept events that match either our sent key or the resolved key.
    const incoming = payload.sessionKey;
    if (incoming !== sessionKey.value && incoming !== resolvedSessionKey.value) {
      // First event for this session — learn the resolved key
      if (streaming.value && !resolvedSessionKey.value) {
        resolvedSessionKey.value = incoming;
      } else {
        return;
      }
    }

    if (payload.state === "delta") {
      const text = extractText(payload.message);
      if (typeof text === "string") {
        // Delta contains full accumulated text
        const current = streamText.value;
        if (!current || text.length >= current.length) {
          streamText.value = text;
        }
      }
    } else if (payload.state === "final") {
      const msg = payload.message as ChatMessage | undefined;
      if (msg) {
        messages.value = [...messages.value, msg];
      } else if (streamText.value.trim()) {
        messages.value = [
          ...messages.value,
          { role: "assistant", content: [{ type: "text", text: streamText.value }], timestamp: Date.now() },
        ];
      }
      _updateLastPreview();
      streamText.value = "";
      streaming.value = false;
      chatRunId.value = null;
      streamStartedAt.value = null;
    } else if (payload.state === "aborted") {
      const msg = payload.message as ChatMessage | undefined;
      if (msg) {
        messages.value = [...messages.value, msg];
      } else if (streamText.value.trim()) {
        messages.value = [
          ...messages.value,
          { role: "assistant", content: [{ type: "text", text: streamText.value }], timestamp: Date.now() },
        ];
      }
      _updateLastPreview();
      streamText.value = "";
      streaming.value = false;
      chatRunId.value = null;
      streamStartedAt.value = null;
    } else if (payload.state === "error") {
      lastError.value = payload.errorMessage ?? "chat error";
      streamText.value = "";
      streaming.value = false;
      chatRunId.value = null;
      streamStartedAt.value = null;
    }
  }

  /** Abort current generation. */
  async function abort() {
    try {
      const key = resolvedSessionKey.value || sessionKey.value;
      await window.openclaw.chat.abort(key);
    } catch {
      // ignore
    }
  }

  /** Start a new session. */
  function newSession() {
    const key = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    sessionKey.value = key;
    resolvedSessionKey.value = null;
    messages.value = [];
    streamText.value = "";
    streaming.value = false;
    chatRunId.value = null;
    streamStartedAt.value = null;
    lastError.value = null;
  }

  /** Update last message preview for current session key. */
  function _updateLastPreview() {
    const key = sessionKey.value;
    const last = [...messages.value].reverse().find((m) => m.role === "assistant" || m.role === "user");
    if (last) {
      const text = extractText(last) || "";
      lastMessageMap.value[key] = text.replace(/\n/g, " ").slice(0, 80);
    }
  }

  return {
    sessionKey,
    resolvedSessionKey,
    messages,
    loading,
    sending,
    streaming,
    streamText,
    streamStartedAt,
    chatRunId,
    lastError,
    wsConnected,
    lastMessageMap,
    extractText,
    switchSession,
    loadHistory,
    sendMessage,
    handleChatEvent,
    abort,
    newSession,
  };
});
