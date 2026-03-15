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

interface SkillEntry {
  id: string;
  name: string;
  description: string;
  source: 'builtin' | 'custom' | 'managed';
  certified: boolean;
  enabled: boolean;
  installed: boolean;
}

interface IntegrityChange {
  skill: string;
  source: string;
  file: string;
  type: "modified" | "added" | "removed";
  expected?: string;
  actual?: string;
}

interface IntegrityResult {
  valid: boolean;
  signatureValid: boolean;
  snapshotExists: boolean;
  changes: IntegrityChange[];
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
  skills: {
    list(): Promise<{ builtin: SkillEntry[]; custom: SkillEntry[]; managed: SkillEntry[] }>;
    updateAllowlist(allowBundled: string[]): Promise<void>;
    updateManagedEntries(entries: Record<string, { enabled: boolean }>): Promise<void>;
    integrityCheck(): Promise<IntegrityResult>;
    pendingIntegrityResult(): Promise<IntegrityResult | null>;
    acceptIntegrityChanges(): Promise<void>;
    generateSnapshot(): Promise<void>;
    onIntegrityAlert(callback: (result: IntegrityResult) => void): () => void;
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
  agents: {
    list(): Promise<{ agents?: { id: string; name: string; description?: string }[] }>;
  };
  channels: {
    list(): Promise<{ channels?: { id: string; name: string; icon: string; type: string; connected: boolean }[] }>;
  };
  model: {
    testConnection(params: { baseUrl: string; apiKey: string; apiFormat: string; modelName: string }): Promise<{ ok: boolean; message: string }>;
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
