/**
 * WebSocket gateway client for OpenClaw — mirrors the webchat protocol.
 *
 * Protocol overview (JSON over WS):
 *   → { type: "req", id, method: "connect", params }   (handshake)
 *   ← { type: "res", id, ok: true, payload: hello }
 *   → { type: "req", id, method: "chat.send",  params: { sessionKey, message } }
 *   ← { type: "res", id, ok: true }
 *   ← { type: "event", event: "chat", payload: { state: "delta"|"final"|"aborted"|"error", ... } }
 */

import WebSocket from "ws";
import { randomUUID } from "crypto";

// ── Types ───────────────────────────────────────────────────────────────

export type GatewayEventFrame = {
  type: "event";
  event: string;
  payload?: unknown;
  seq?: number;
};

export type GatewayResponseFrame = {
  type: "res";
  id: string;
  ok: boolean;
  payload?: unknown;
  error?: { code: string; message: string };
};

export type ChatEventPayload = {
  runId: string;
  sessionKey: string;
  state: "delta" | "final" | "aborted" | "error";
  message?: unknown;
  errorMessage?: string;
};

type Pending = {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
};

export type GatewayClientOptions = {
  port: number;
  token: string;
  onEvent?: (evt: GatewayEventFrame) => void;
  onConnected?: () => void;
  onDisconnected?: (reason: string) => void;
};

// ── Client ──────────────────────────────────────────────────────────────

export class GatewayClient {
  private ws: WebSocket | null = null;
  private pending = new Map<string, Pending>();
  private closed = false;
  private backoffMs = 800;
  private _connected = false;
  private connectNonce: string | null = null;
  private connectSent = false;
  private connectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private opts: GatewayClientOptions) {}

  get connected() {
    return this._connected;
  }

  start() {
    this.closed = false;
    this.connect();
  }

  stop() {
    this.closed = true;
    this._connected = false;
    this.ws?.close();
    this.ws = null;
    this.flushPending("client stopped");
  }

  // ── Public API ──

  async request<T = unknown>(method: string, params?: unknown): Promise<T> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error("gateway not connected");
    }
    const id = randomUUID();
    const frame = { type: "req", id, method, params };
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: (v) => resolve(v as T),
        reject,
      });
      this.ws!.send(JSON.stringify(frame));
    });
  }

  /** Send a chat message (server maintains history). */
  sendChat(sessionKey: string, message: string): Promise<unknown> {
    return this.request("chat.send", {
      sessionKey,
      message,
      deliver: false,
      idempotencyKey: randomUUID(),
    });
  }

  /** Load chat history for a session. */
  loadHistory(sessionKey: string): Promise<{ messages?: unknown[]; thinkingLevel?: string }> {
    return this.request("chat.history", { sessionKey, limit: 200 });
  }

  /** Abort the current chat run. */
  abortChat(sessionKey: string): Promise<unknown> {
    return this.request("chat.abort", { sessionKey });
  }

  // ── Internal ──

  private connect() {
    if (this.closed) return;

    const url = `ws://127.0.0.1:${this.opts.port}/`;
    this.ws = new WebSocket(url, {
      headers: { Origin: `http://127.0.0.1:${this.opts.port}` },
    });
    this.connectNonce = null;
    this.connectSent = false;

    this.ws.on("open", () => {
      // Queue connect with a delay — gateway may send connect.challenge first
      this.queueConnect();
    });

    this.ws.on("message", (data) => {
      this.handleMessage(String(data));
    });

    this.ws.on("close", (_code, reason) => {
      this._connected = false;
      this.ws = null;
      this.flushPending("disconnected");
      this.opts.onDisconnected?.(String(reason || "closed"));
      this.scheduleReconnect();
    });

    this.ws.on("error", () => {
      // close handler will fire; nothing extra needed
    });
  }

  private queueConnect() {
    this.connectSent = false;
    if (this.connectTimer !== null) {
      clearTimeout(this.connectTimer);
    }
    this.connectTimer = setTimeout(() => {
      this.connectTimer = null;
      this.sendConnect();
    }, 750);
  }

  private sendConnect() {
    if (this.connectSent) return;
    this.connectSent = true;
    if (this.connectTimer !== null) {
      clearTimeout(this.connectTimer);
      this.connectTimer = null;
    }
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    const params: Record<string, unknown> = {
      minProtocol: 3,
      maxProtocol: 3,
      client: {
        id: "gateway-client",
        version: "1.0.0",
        platform: process.platform,
        mode: "backend",
      },
      role: "operator",
      scopes: ["operator.admin"],
      caps: ["tool-events"],
    };

    if (this.opts.token) {
      params.auth = { token: this.opts.token };
    }

    this.request<Record<string, unknown>>("connect", params)
      .then(() => {
        this._connected = true;
        this.backoffMs = 800;
        this.opts.onConnected?.();
      })
      .catch((err) => {
        console.error("[gateway-client] connect handshake failed:", err.message);
        // Don't reconnect for auth errors — they won't resolve on retry
        const isAuthError = /unauthorized|token.*mismatch|rate.limited/i.test(err.message);
        if (isAuthError) {
          this.closed = true; // prevent auto-reconnect
        }
        this.ws?.close();
      });
  }

  private scheduleReconnect() {
    if (this.closed) return;
    const delay = this.backoffMs;
    this.backoffMs = Math.min(this.backoffMs * 1.7, 15_000);
    setTimeout(() => this.connect(), delay);
  }

  private flushPending(reason: string) {
    for (const [, p] of this.pending) {
      p.reject(new Error(reason));
    }
    this.pending.clear();
  }

  private handleMessage(raw: string) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return;
    }

    const frame = parsed as { type?: string };

    if (frame.type === "event") {
      const evt = parsed as GatewayEventFrame;
      // Handle connect.challenge — gateway may require a nonce handshake
      if (evt.event === "connect.challenge") {
        const payload = evt.payload as { nonce?: string } | undefined;
        if (payload?.nonce) {
          this.connectNonce = payload.nonce;
          // Challenge arrived — reset sent flag and send immediately
          this.connectSent = false;
          this.sendConnect();
        }
        return;
      }
      this.opts.onEvent?.(evt);
      return;
    }

    if (frame.type === "res") {
      const res = parsed as GatewayResponseFrame;
      const p = this.pending.get(res.id);
      if (!p) return;
      this.pending.delete(res.id);
      if (res.ok) {
        p.resolve(res.payload);
      } else {
        p.reject(
          new Error(res.error?.message ?? "request failed")
        );
      }
    }
  }
}
