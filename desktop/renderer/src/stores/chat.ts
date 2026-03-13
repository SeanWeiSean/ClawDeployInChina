import { defineStore } from "pinia";
import { ref } from "vue";
import { useSessionStore } from "./sessions";

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
  const sessionKey = ref("main");
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

  // ── Per-session streaming state cache ──
  // When switching away from a session that is still streaming,
  // we save its streaming state here so it can be restored later.
  interface SessionStreamState {
    streaming: boolean;
    streamText: string;
    streamStartedAt: number | null;
    chatRunId: string | null;
    resolvedSessionKey: string | null;
    messages: ChatMessage[];
    sending: boolean;
  }
  const sessionStateCache = new Map<string, SessionStreamState>();

  /** Save current session's volatile state into the cache. */
  function _saveCurrentState() {
    const key = sessionKey.value;
    if (!key) return;
    if (streaming.value || sending.value) {
      sessionStateCache.set(key, {
        streaming: streaming.value,
        streamText: streamText.value,
        streamStartedAt: streamStartedAt.value,
        chatRunId: chatRunId.value,
        resolvedSessionKey: resolvedSessionKey.value,
        messages: [...messages.value],
        sending: sending.value,
      });
    } else {
      sessionStateCache.delete(key);
    }
  }

  /** Restore a session's volatile state from the cache (returns true if restored). */
  function _restoreState(key: string): boolean {
    const cached = sessionStateCache.get(key);
    if (!cached) return false;
    streaming.value = cached.streaming;
    streamText.value = cached.streamText;
    streamStartedAt.value = cached.streamStartedAt;
    chatRunId.value = cached.chatRunId;
    resolvedSessionKey.value = cached.resolvedSessionKey;
    messages.value = cached.messages;
    sending.value = cached.sending;
    return true;
  }

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
    // Save the current session's volatile state (including streaming)
    _syncToSessionStore();
    _saveCurrentState();

    sessionKey.value = key;
    const sessionStore = useSessionStore();
    sessionStore.ensureSession(key);

    // Try to restore cached state (streaming session we switched away from)
    if (_restoreState(key)) {
      return; // restored — don't overwrite with loadHistory
    }

    resolvedSessionKey.value = null;
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
      // Remove from cache since we now have authoritative data
      sessionStateCache.delete(sessionKey.value);
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
    const incoming = payload.sessionKey;

    // Check if this event belongs to the current active session
    const isActive = incoming === sessionKey.value || incoming === resolvedSessionKey.value;

    // Check if this event belongs to a background (cached) session
    if (!isActive) {
      // Try to match against cached sessions' resolved keys
      for (const [cachedKey, cached] of sessionStateCache) {
        if (incoming === cachedKey || incoming === cached.resolvedSessionKey) {
          _handleBackgroundEvent(cachedKey, cached, payload);
          return;
        }
      }
      // First event for active session — learn the resolved key
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
      // Reload history to get the authoritative server-side version (like webchat)
      loadHistory();
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

  /** Start a new session (preserves the old one). */
  function newSession() {
    // Save the current session before switching
    _syncToSessionStore();

    const key = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    sessionKey.value = key;
    resolvedSessionKey.value = null;
    messages.value = [];
    streamText.value = "";
    streaming.value = false;
    chatRunId.value = null;
    streamStartedAt.value = null;
    lastError.value = null;

    const sessionStore = useSessionStore();
    sessionStore.ensureSession(key);
  }

  /** Update last message preview for current session key. */
  function _updateLastPreview() {
    const key = sessionKey.value;
    const last = [...messages.value].reverse().find((m) => m.role === "assistant" || m.role === "user");
    if (last) {
      const text = extractText(last) || "";
      lastMessageMap.value[key] = text.replace(/\n/g, " ").slice(0, 80);
    }
    _syncToSessionStore();
  }

  /** Sync current session state to the sessions store. */
  function _syncToSessionStore() {
    const key = sessionKey.value;
    if (!key) return;
    const sessionStore = useSessionStore();
    sessionStore.ensureSession(key);
    // Auto-title from first user message
    const firstUser = messages.value.find((m) => m.role === "user");
    if (firstUser) {
      sessionStore.autoTitle(key, extractText(firstUser) || "");
    }
    // Update preview
    const last = [...messages.value].reverse().find((m) => m.role === "assistant" || m.role === "user");
    if (last) {
      sessionStore.updateSession(key, { preview: (extractText(last) || "").replace(/\n/g, " ").slice(0, 80) });
    }
  }

  /** Handle a chat event for a background (non-active) session stored in the cache. */
  function _handleBackgroundEvent(cachedKey: string, cached: SessionStreamState, payload: ChatEventPayload) {
    if (payload.state === "delta") {
      const text = extractText(payload.message);
      if (typeof text === "string") {
        if (!cached.streamText || text.length >= cached.streamText.length) {
          cached.streamText = text;
        }
      }
    } else if (payload.state === "final") {
      const msg = payload.message as ChatMessage | undefined;
      if (msg) {
        cached.messages = [...cached.messages, msg];
      } else if (cached.streamText.trim()) {
        cached.messages = [
          ...cached.messages,
          { role: "assistant", content: [{ type: "text", text: cached.streamText }], timestamp: Date.now() },
        ];
      }
      cached.streaming = false;
      cached.streamText = "";
      cached.chatRunId = null;
      cached.streamStartedAt = null;
      cached.sending = false;
      // Keep in cache so switching back restores final messages
      sessionStateCache.set(cachedKey, cached);
    } else if (payload.state === "aborted") {
      const msg = payload.message as ChatMessage | undefined;
      if (msg) {
        cached.messages = [...cached.messages, msg];
      } else if (cached.streamText.trim()) {
        cached.messages = [
          ...cached.messages,
          { role: "assistant", content: [{ type: "text", text: cached.streamText }], timestamp: Date.now() },
        ];
      }
      cached.streaming = false;
      cached.streamText = "";
      cached.chatRunId = null;
      cached.streamStartedAt = null;
      cached.sending = false;
      sessionStateCache.set(cachedKey, cached);
    } else if (payload.state === "error") {
      cached.streaming = false;
      cached.streamText = "";
      cached.chatRunId = null;
      cached.streamStartedAt = null;
      cached.sending = false;
      sessionStateCache.set(cachedKey, cached);
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
