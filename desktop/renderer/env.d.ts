/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

interface ChatEventPayload {
  runId: string;
  sessionKey: string;
  state: "delta" | "final" | "aborted" | "error";
  message?: unknown;
  errorMessage?: string;
}

interface AppSettings {
  language: string;
  autoStart: boolean;
  startMinimized: boolean;
  themeMode: string;
  accentColor: string;
}

interface OpenClawAPI {
  gateway: {
    getPort(): Promise<number>;
    getToken(): Promise<string>;
    getStatus(): Promise<string>;
    restart(): Promise<void>;
    onStatus(callback: (status: string) => void): () => void;
    onLog(callback: (msg: string) => void): () => void;
    onWsConnected(callback: (mainSessionKey: string | null) => void): () => void;
    onWsDisconnected(callback: (reason: string) => void): () => void;
  };
  config: {
    getStateDir(): Promise<string>;
    isConfigured(): Promise<boolean>;
    read(): Promise<any>;
    write(config: any): Promise<void>;
  };
  settings: {
    get(): Promise<AppSettings>;
    set(key: string, value: any): Promise<void>;
  };
  chat: {
    isConnected(): Promise<boolean>;
    sendMessage(sessionKey: string, message: string): Promise<void>;
    loadHistory(sessionKey: string): Promise<{ messages?: unknown[]; thinkingLevel?: string }>;
    abort(sessionKey: string): Promise<void>;
    onEvent(callback: (payload: ChatEventPayload) => void): () => void;
  };
  cron: {
    list(): Promise<{ jobs?: unknown[] }>;
  };
  window: {
    minimize(): Promise<void>;
    maximize(): Promise<void>;
    close(): Promise<void>;
  };
}

interface Window {
  openclaw: OpenClawAPI;
}
