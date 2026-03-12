import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("openclaw", {
  // --- Gateway lifecycle ---
  gateway: {
    getPort: () => ipcRenderer.invoke("gateway:get-port"),
    getToken: () => ipcRenderer.invoke("gateway:get-token"),
    getStatus: () => ipcRenderer.invoke("gateway:get-status"),
    restart: () => ipcRenderer.invoke("gateway:restart"),
    onStatus: (callback: (status: string) => void) => {
      const handler = (_event: any, status: string) => callback(status);
      ipcRenderer.on("gateway:status", handler);
      return () => ipcRenderer.removeListener("gateway:status", handler);
    },
    onLog: (callback: (msg: string) => void) => {
      const handler = (_event: any, msg: string) => callback(msg);
      ipcRenderer.on("gateway:log", handler);
      return () => ipcRenderer.removeListener("gateway:log", handler);
    },
    onWsConnected: (callback: (mainSessionKey: string | null) => void) => {
      const handler = (_event: any, key: string | null) => callback(key);
      ipcRenderer.on("gateway:ws-connected", handler);
      return () => ipcRenderer.removeListener("gateway:ws-connected", handler);
    },
    onWsDisconnected: (callback: (reason: string) => void) => {
      const handler = (_event: any, reason: string) => callback(reason);
      ipcRenderer.on("gateway:ws-disconnected", handler);
      return () => ipcRenderer.removeListener("gateway:ws-disconnected", handler);
    },
  },

  // --- Configuration ---
  config: {
    getStateDir: () => ipcRenderer.invoke("config:get-state-dir"),
    isConfigured: () => ipcRenderer.invoke("config:is-configured"),
    read: () => ipcRenderer.invoke("config:read"),
    write: (config: any) => ipcRenderer.invoke("config:write", config),
  },

  // --- Settings ---
  settings: {
    get: () => ipcRenderer.invoke("settings:get"),
    set: (key: string, value: any) => ipcRenderer.invoke("settings:set", key, value),
  },

  // --- Chat (session-based via WebSocket gateway protocol) ---
  chat: {
    /** Check if the WS gateway connection is alive. */
    isConnected: () => ipcRenderer.invoke("chat:is-connected"),

    /** Send a message to a session. Server maintains history. */
    sendMessage: (sessionKey: string, message: string) =>
      ipcRenderer.invoke("chat:send-message", { sessionKey, message }),

    /** Load chat history for a session. */
    loadHistory: (sessionKey: string) =>
      ipcRenderer.invoke("chat:load-history", { sessionKey }),

    /** Abort the current run on a session. */
    abort: (sessionKey: string) =>
      ipcRenderer.invoke("chat:abort", { sessionKey }),

    /**
     * Subscribe to chat events (delta, final, aborted, error).
     * Returns an unsubscribe function.
     */
    onEvent: (callback: (payload: {
      runId: string;
      sessionKey: string;
      state: "delta" | "final" | "aborted" | "error";
      message?: unknown;
      errorMessage?: string;
    }) => void) => {
      const handler = (_event: any, payload: any) => callback(payload);
      ipcRenderer.on("chat:event", handler);
      return () => ipcRenderer.removeListener("chat:event", handler);
    },
  },

  // --- Cron / Scheduled Tasks ---
  cron: {
    list: () => ipcRenderer.invoke("cron:list"),
  },

  // --- Window ---
  window: {
    minimize: () => ipcRenderer.invoke("window:minimize"),
    maximize: () => ipcRenderer.invoke("window:maximize"),
    close: () => ipcRenderer.invoke("window:close"),
  },
});
