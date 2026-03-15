import { app, BrowserWindow, ipcMain, Menu } from "electron";
import * as path from "path";
import * as fs from "fs";
import * as http from "http";
import { ChildProcess, spawn } from "child_process";
import { GatewayClient, type ChatEventPayload } from "./gateway-client";
import { createTray, updateTrayMenu } from "./tray";
import Store from "electron-store";
import { verifySkillIntegrity, generateAndSignSnapshot, getSkillSourceDirs, type IntegrityResult } from "./skill-integrity";

// Handle EPIPE errors on stdout/stderr (happens when parent terminal closes)
process.on("uncaughtException", (err: NodeJS.ErrnoException) => {
  if (err.code === "EPIPE") {
    // Log to file instead of crashing — stdout/stderr pipe is broken
    const logPath = path.join(
      process.env.OPENCLAW_STATE_DIR || path.join(process.env.APPDATA || "", "openclaw"),
      "epipe.log"
    );
    try {
      fs.appendFileSync(logPath, `[${new Date().toISOString()}] EPIPE: ${err.stack}\n`);
    } catch { /* best-effort */ }
    return;
  }
  throw err;
});

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const store = new Store<{ windowBounds: Electron.Rectangle | null }>({
  defaults: { windowBounds: null },
});

const settingsStore = new Store<{
  language: string;
  autoStart: boolean;
  startMinimized: boolean;
  themeMode: string;
  accentColor: string;
}>({
  name: 'settings',
  defaults: {
    language: 'zh-CN',
    autoStart: false,
    startMinimized: false,
    themeMode: 'light',
    accentColor: '#4a90d9',
  },
});

let mainWindow: BrowserWindow | null = null;
let gatewayProcess: ChildProcess | null = null;
let gwClient: GatewayClient | null = null;
let gatewayPort = 0;
let gatewayToken = "";
let gatewayStatus = "stopped";
let pendingIntegrityResult: IntegrityResult | null = null;

// ---------------------------------------------------------------------------
// Skill file watcher — detects mid-session tampering
// ---------------------------------------------------------------------------
let skillWatchers: fs.FSWatcher[] = [];
let watcherDebounceTimer: ReturnType<typeof setTimeout> | null = null;

function startSkillFileWatcher(): void {
  // Clean up any existing watchers
  for (const w of skillWatchers) { try { w.close(); } catch {} }
  skillWatchers = [];

  for (const { baseDir } of getSkillSourceDirs()) {
    if (!fs.existsSync(baseDir)) continue;
    try {
      const watcher = fs.watch(baseDir, { recursive: true }, () => {
        // Debounce — multiple FS events fire for a single change
        if (watcherDebounceTimer) clearTimeout(watcherDebounceTimer);
        watcherDebounceTimer = setTimeout(() => {
          console.log("Skill file change detected — running integrity check...");
          const result = verifySkillIntegrity();
          if (!result.valid && mainWindow) {
            mainWindow.webContents.send("skills:integrity-alert", result);
          }
        }, 2000);
      });
      skillWatchers.push(watcher);
      console.log(`Watching skill directory: ${baseDir}`);
    } catch (err) {
      console.warn(`Failed to watch ${baseDir}:`, err);
    }
  }
}

// ---------------------------------------------------------------------------
// Path helpers
// ---------------------------------------------------------------------------
function getOpenClawStateDir(): string {
  if (process.env.OPENCLAW_STATE_DIR) {
    return process.env.OPENCLAW_STATE_DIR;
  }
  // Prefer ~/.openclaw (where the gateway actually reads from)
  const homeDir = path.join(app.getPath("home"), ".openclaw");
  if (fs.existsSync(path.join(homeDir, "openclaw.json"))) {
    return homeDir;
  }
  // Fallback to %APPDATA%/openclaw (deployer writes here)
  return path.join(app.getPath("appData"), "openclaw");
}

function getConfigPath(): string {
  return path.join(getOpenClawStateDir(), "openclaw.json");
}

function readConfig(): any {
  try {
    return JSON.parse(fs.readFileSync(getConfigPath(), "utf-8"));
  } catch {
    return null;
  }
}

function isConfigured(): boolean {
  const config = readConfig();
  return !!(config?.gateway);
}

// ---------------------------------------------------------------------------
// Renderer URL (Vite dev server vs built files)
// ---------------------------------------------------------------------------
const isDev = !app.isPackaged;
const VITE_DEV_URL = "http://localhost:5173";

function getRendererURL(): string {
  if (isDev) return VITE_DEV_URL;
  return `file://${path.join(__dirname, "../renderer/dist/index.html")}`;
}

// ---------------------------------------------------------------------------
// Window creation
// ---------------------------------------------------------------------------
function createMainWindow(): BrowserWindow {
  const savedBounds = store.get("windowBounds");
  const win = new BrowserWindow({
    width: savedBounds?.width || 1200,
    height: savedBounds?.height || 800,
    x: savedBounds?.x,
    y: savedBounds?.y,
    title: "MicroClawDesktop",
    icon: path.join(__dirname, "../assets/microclaw.png"),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const saveBounds = () => {
    if (!win.isMinimized() && !win.isMaximized()) {
      store.set("windowBounds", win.getBounds());
    }
  };
  win.on("resize", saveBounds);
  win.on("move", saveBounds);

  // Minimize to tray instead of closing
  win.on("close", (e) => {
    if (!(app as any).isQuitting) {
      e.preventDefault();
      win.hide();
    }
  });

  Menu.setApplicationMenu(null);
  win.once("ready-to-show", () => {
    if (!settingsStore.get('startMinimized')) {
      win.show();
    }
  });

  return win;
}

// ---------------------------------------------------------------------------
// Gateway management
// ---------------------------------------------------------------------------

/** Check if an existing gateway is running on the given port */
function checkExistingGateway(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(
      `http://127.0.0.1:${port}/health`,
      { timeout: 2000 },
      (res) => resolve(res.statusCode === 200)
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

/** Resolve path to node.exe */
function resolveNodePath(): string {
  if (app.isPackaged) {
    const bundled = path.join(process.resourcesPath, "node.exe");
    if (fs.existsSync(bundled)) return bundled;
  }
  const ocNode = process.env.USERPROFILE
    ? path.join(process.env.USERPROFILE, ".openclaw-node", "node.exe")
    : "";
  if (ocNode && fs.existsSync(ocNode)) return ocNode;
  return "node";
}

/** Resolve path to openclaw entry */
function resolveOpenClawEntry(): string {
  if (app.isPackaged) {
    const bundled = path.join(process.resourcesPath, "openclaw", "openclaw.mjs");
    if (fs.existsSync(bundled)) return bundled;
  }
  const candidates = [
    process.env.USERPROFILE
      ? path.join(process.env.USERPROFILE, ".openclaw-node", "node_modules", "openclaw", "openclaw.mjs")
      : "",
    process.env.USERPROFILE
      ? path.join(process.env.USERPROFILE, ".openclaw-node", "node_modules", "openclaw", "dist", "index.js")
      : "",
    process.env.APPDATA
      ? path.join(process.env.APPDATA, "npm", "node_modules", "openclaw", "openclaw.mjs")
      : "",
    process.env.APPDATA
      ? path.join(process.env.APPDATA, "npm", "node_modules", "openclaw", "dist", "index.js")
      : "",
  ];
  for (const p of candidates) {
    if (p && fs.existsSync(p)) return p;
  }
  return candidates[0];
}

/** Wait for gateway health check to pass */
async function waitForGatewayReady(port: number, timeoutMs = 30000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const ok = await checkExistingGateway(port);
    if (ok) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

/** Stop the gateway CMD process */
function stopGatewayProcess(): void {
  if (gatewayProcess && gatewayProcess.pid) {
    try {
      spawn("taskkill", ["/pid", String(gatewayProcess.pid), "/T", "/F"], {
        windowsHide: true,
      });
    } catch {}
    gatewayProcess = null;
  }
}

async function startGateway(): Promise<void> {
  // Read config to get token and configured port
  const config = readConfig();
  gatewayToken = config?.gateway?.auth?.token || "";
  const configuredPort = config?.gateway?.port || 18789;

  // Check if a gateway is already running (e.g. started by deployer)
  // Retry a few times since gateway may still be starting up
  for (let attempt = 0; attempt < 5; attempt++) {
    const existing = await checkExistingGateway(configuredPort);
    if (existing) {
      gatewayPort = configuredPort;
      gatewayStatus = "running";
      mainWindow?.webContents.send("gateway:status", "running");
      console.log(`Connected to existing gateway on port ${configuredPort}`);
      connectGatewayWs();
      return;
    }
    if (attempt < 4) {
      await new Promise((r) => setTimeout(r, 3000));
    }
  }

  // No existing gateway — launch in a visible CMD window
  gatewayPort = configuredPort;
  const stateDir = getOpenClawStateDir();
  const nodePath = resolveNodePath();
  const entryPath = resolveOpenClawEntry();

  if (!fs.existsSync(nodePath)) {
    console.error(`node.exe not found at ${nodePath}`);
    gatewayStatus = "failed";
    mainWindow?.webContents.send("gateway:status", "failed");
    return;
  }
  if (!fs.existsSync(entryPath)) {
    console.error(`openclaw entry not found at ${entryPath}`);
    gatewayStatus = "failed";
    mainWindow?.webContents.send("gateway:status", "failed");
    return;
  }

  const cmdLine = `"${nodePath}" "${entryPath}" gateway run --port ${configuredPort} --bind loopback --force --allow-unconfigured`;
  console.log(`Launching gateway CMD: ${cmdLine}`);

  gatewayProcess = spawn("cmd.exe", ["/K", `title OpenClaw Gateway && ${cmdLine}`], {
    cwd: path.dirname(entryPath),
    env: {
      ...process.env,
      OPENCLAW_STATE_DIR: stateDir,
      NODE_ENV: "production",
    },
    detached: true,
    stdio: "ignore",
  });

  gatewayProcess.on("error", (err) => {
    console.error("Gateway CMD spawn error:", err);
    gatewayProcess = null;
    gatewayStatus = "failed";
    mainWindow?.webContents.send("gateway:status", "failed");
  });

  // Wait for gateway to become ready
  gatewayStatus = "starting";
  mainWindow?.webContents.send("gateway:status", "starting");

  const ready = await waitForGatewayReady(configuredPort);
  if (ready) {
    gatewayStatus = "running";
    mainWindow?.webContents.send("gateway:status", "running");
    connectGatewayWs();
  } else {
    gatewayStatus = "timeout";
    mainWindow?.webContents.send("gateway:status", "timeout");
  }
}

// ---------------------------------------------------------------------------
// WebSocket gateway client — mirrors the webchat protocol
// ---------------------------------------------------------------------------

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

function connectGatewayWs(): void {
  gwClient?.stop();

  gwClient = new GatewayClient({
    port: gatewayPort,
    token: gatewayToken,
    onConnected: (hello) => {
      console.log("[gateway-ws] connected");
      // Extract the canonical session key from hello → snapshot → sessionDefaults
      const snapshot = hello?.snapshot as Record<string, unknown> | undefined;
      const sessionDefaults = snapshot?.sessionDefaults as Record<string, unknown> | undefined;
      const mainSessionKey = sessionDefaults?.mainSessionKey as string | undefined;
      mainWindow?.webContents.send("gateway:ws-connected", mainSessionKey || null);
    },
    onDisconnected: (reason) => {
      console.log(`[gateway-ws] disconnected: ${reason}`);
      mainWindow?.webContents.send("gateway:ws-disconnected", reason);
    },
    onEvent: (evt) => {
      if (evt.event === "chat") {
        const payload = evt.payload as ChatEventPayload | undefined;
        if (!payload) return;
        console.log(`[chat:event] state=${payload.state} sessionKey=${payload.sessionKey}`);
        mainWindow?.webContents.send("chat:event", payload);
      }
    },
  });
  gwClient.start();
}

// ---------------------------------------------------------------------------
// IPC Handlers
// ---------------------------------------------------------------------------
function registerIpcHandlers(): void {
  // --- Gateway ---
  ipcMain.handle("gateway:get-port", () => gatewayPort);
  ipcMain.handle("gateway:get-token", () => gatewayToken);
  ipcMain.handle("gateway:get-status", () => gatewayStatus);
  ipcMain.handle("gateway:restart", async () => {
    stopGatewayProcess();
    await new Promise((r) => setTimeout(r, 1000));
    await startGateway();
  });

  // --- Config ---
  ipcMain.handle("config:get-state-dir", () => getOpenClawStateDir());
  ipcMain.handle("config:is-configured", () => isConfigured());
  ipcMain.handle("config:read", () => readConfig());
  ipcMain.handle("config:write", (_event, config: any) => {
    const stateDir = getOpenClawStateDir();
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(getConfigPath(), JSON.stringify(config, null, 2), "utf-8");
  });

  // --- Skills ---
  ipcMain.handle("skills:list", () => {
    const homeDir = app.getPath("home");
    const builtinDir = path.join(homeDir, ".openclaw-node", "node_modules", "openclaw", "skills");
    const customDir = path.join(homeDir, ".agents", "skills");
    const managedDir = path.join(homeDir, ".openclaw", "skills");

    // Load certification catalog (builtin)
    let catalog: Record<string, { description: string; certified: boolean }> = {};
    try {
      const catalogPath = path.join(getOpenClawStateDir(), "skill_catalog.json");
      if (fs.existsSync(catalogPath)) {
        catalog = JSON.parse(fs.readFileSync(catalogPath, "utf-8"));
      }
    } catch { /* catalog unavailable — all skills show as uncertified */ }

    // Load managed skill catalog
    let managedCatalog: Record<string, { description: string; certified: boolean }> = {};
    try {
      const managedCatalogPath = path.join(getOpenClawStateDir(), "managed_skill_catalog.json");
      if (fs.existsSync(managedCatalogPath)) {
        managedCatalog = JSON.parse(fs.readFileSync(managedCatalogPath, "utf-8"));
      }
    } catch {}

    // Load allowBundled and entries from config
    const config = readConfig();
    const allowBundled: string[] | undefined = config?.skills?.allowBundled;
    const entries: Record<string, { enabled: boolean }> = config?.skills?.entries ?? {};

    function scanSkills(dir: string, source: "builtin" | "custom" | "managed"): any[] {
      const results: any[] = [];
      if (!fs.existsSync(dir)) return results;
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        const skillMd = path.join(dir, entry.name, "SKILL.md");
        let name = entry.name;
        let description = "";
        if (fs.existsSync(skillMd)) {
          const head = fs.readFileSync(skillMd, "utf-8").slice(0, 1000);
          const nameMatch = head.match(/^name:\s*(.+)/m);
          const descMatch = head.match(/^description:\s*(.+)/m);
          if (nameMatch) name = nameMatch[1].trim();
          if (descMatch) description = descMatch[1].replace(/^["']|["']$/g, "").trim();
        }

        let certified = false;
        let enabled = true;

        if (source === "managed") {
          certified = managedCatalog[entry.name]?.certified ?? false;
          enabled = entries[entry.name]?.enabled ?? certified;
          if (!description && managedCatalog[entry.name]?.description) {
            description = managedCatalog[entry.name].description;
          }
        } else {
          certified = catalog[entry.name]?.certified ?? false;
          if (source === "builtin" && allowBundled && allowBundled.length > 0) {
            enabled = allowBundled.includes(entry.name);
          }
        }

        results.push({ id: entry.name, name, description, source, certified, enabled, installed: true });
      }
      return results;
    }

    const builtin = scanSkills(builtinDir, "builtin");
    const custom = scanSkills(customDir, "custom");
    const managedOnDisk = scanSkills(managedDir, "managed");

    // Also list catalog-only managed skills (defined in catalog but not yet on disk)
    const onDiskIds = new Set(managedOnDisk.map(s => s.id));
    for (const [id, info] of Object.entries(managedCatalog)) {
      if (!onDiskIds.has(id)) {
        const enabled = entries[id]?.enabled ?? info.certified;
        managedOnDisk.push({
          id, name: id, description: info.description,
          source: "managed" as const, certified: info.certified, enabled,
          installed: false,
        });
      }
    }

    return { builtin, custom, managed: managedOnDisk };
  });

  ipcMain.handle("skills:update-allowlist", (_event, allowBundled: string[]) => {
    const config = readConfig() || {};
    if (!config.skills) config.skills = {};
    config.skills.allowBundled = allowBundled;
    const stateDir = getOpenClawStateDir();
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(getConfigPath(), JSON.stringify(config, null, 2), "utf-8");
  });

  ipcMain.handle("skills:update-managed-entries",
    (_event, updatedEntries: Record<string, { enabled: boolean }>) => {
      const config = readConfig() || {};
      if (!config.skills) config.skills = {};
      if (!config.skills.entries) config.skills.entries = {};
      Object.assign(config.skills.entries, updatedEntries);
      const stateDir = getOpenClawStateDir();
      fs.mkdirSync(stateDir, { recursive: true });
      fs.writeFileSync(getConfigPath(), JSON.stringify(config, null, 2), "utf-8");
    }
  );

  ipcMain.handle("skills:integrity-check", (): IntegrityResult => {
    return verifySkillIntegrity();
  });

  ipcMain.handle("skills:generate-snapshot", () => {
    generateAndSignSnapshot();
  });

  ipcMain.handle("skills:pending-integrity-result", (): IntegrityResult | null => {
    return pendingIntegrityResult;
  });

  ipcMain.handle("skills:accept-integrity-changes", () => {
    generateAndSignSnapshot();
    pendingIntegrityResult = null;
  });

  // --- Chat (WebSocket gateway protocol) ---
  ipcMain.handle("chat:send-message", async (_event, params: { sessionKey: string; message: string }) => {
    if (!gwClient?.connected) throw new Error("Gateway not connected");
    await gwClient.sendChat(params.sessionKey, params.message);
  });

  ipcMain.handle("chat:load-history", async (_event, params: { sessionKey: string }) => {
    if (!gwClient?.connected) throw new Error("Gateway not connected");
    return await gwClient.loadHistory(params.sessionKey);
  });

  ipcMain.handle("chat:abort", async (_event, params: { sessionKey: string }) => {
    if (!gwClient?.connected) throw new Error("Gateway not connected");
    await gwClient.abortChat(params.sessionKey);
  });

  ipcMain.handle("chat:is-connected", () => gwClient?.connected ?? false);

  // --- Cron / Scheduled Tasks ---
  ipcMain.handle("cron:list", async () => {
    if (!gwClient?.connected) throw new Error("Gateway not connected");
    return await gwClient.listCronJobs();
  });

  // --- Agents ---
  ipcMain.handle("agents:list", async () => {
    if (!gwClient?.connected) return { agents: [] };
    try {
      return await gwClient.listAgents();
    } catch (err) {
      console.warn("[agents:list] failed:", err);
      return { agents: [] };
    }
  });

  // --- Channels ---
  ipcMain.handle("channels:list", async () => {
    if (!gwClient?.connected) return { channels: [] };
    try {
      return await gwClient.listChannels();
    } catch (err) {
      console.warn("[channels:list] failed:", err);
      return { channels: [] };
    }
  });

  // --- Model connection test (runs in main process to avoid CORS) ---
  ipcMain.handle("model:test-connection", async (_event, params: {
    baseUrl: string; apiKey: string; apiFormat: string; modelName: string;
  }) => {
    const { baseUrl, apiKey, apiFormat, modelName } = params;
    const base = baseUrl.replace(/\/$/, "");
    try {
      if (apiFormat === "anthropic") {
        const res = await fetch(base + "/v1/messages", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": apiKey,
            "anthropic-version": "2023-06-01",
          },
          body: JSON.stringify({
            model: modelName || "claude-3-haiku-20240307",
            max_tokens: 1,
            messages: [{ role: "user", content: "hi" }],
          }),
        });
        if (res.ok || res.status === 400) {
          return { ok: true, message: "Connection successful (Anthropic)" };
        }
        return { ok: false, message: `Failed: HTTP ${res.status} ${res.statusText}` };
      } else {
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
        const res = await fetch(base + "/chat/completions", {
          method: "POST",
          headers,
          body: JSON.stringify({
            model: modelName || "gpt-4o",
            max_tokens: 1,
            messages: [{ role: "user", content: "hi" }],
          }),
        });
        if (res.ok || res.status === 400) {
          return { ok: true, message: "Connection successful (OpenAI)" };
        }
        return { ok: false, message: `Failed: HTTP ${res.status} ${res.statusText}` };
      }
    } catch (err: any) {
      return { ok: false, message: "Connection failed: " + (err.message || "Network error") };
    }
  });

  // --- Usage (LiteLLM spend) ---
  ipcMain.handle("usage:get-stats", async () => {
    const config = readConfig();
    if (!config) throw new Error("配置文件未找到");

    // Get LiteLLM proxy base URL from config providers
    const providers = config?.models?.providers || {};
    const litellm = providers.litellm || (Object.values(providers)[0] as any);
    if (!litellm?.baseUrl) throw new Error("模型提供商未配置");
    let baseUrl: string = litellm.baseUrl;
    if (baseUrl.endsWith("/v1")) baseUrl = baseUrl.slice(0, -3);
    baseUrl = baseUrl.replace(/\/$/, "");

    // Get API key from .env file in state dir
    let apiKey = "";
    const envPath = path.join(getOpenClawStateDir(), ".env");
    if (fs.existsSync(envPath)) {
      const envContent = fs.readFileSync(envPath, "utf-8");
      const match = envContent.match(/LITELLM_API_KEY=(.+)/);
      if (match) apiKey = match[1].trim();
    }
    if (!apiKey) apiKey = process.env.LITELLM_API_KEY || "";
    if (!apiKey) throw new Error("API Key 未找到");

    // Query /key/info for spend summary
    const keyInfoRes = await fetch(`${baseUrl}/key/info`, {
      headers: { "Authorization": `Bearer ${apiKey}` },
    });
    if (!keyInfoRes.ok) {
      throw new Error(`LiteLLM API 错误: ${keyInfoRes.status} ${keyInfoRes.statusText}`);
    }
    const keyInfo = (await keyInfoRes.json()) as any;
    const info = keyInfo.info || keyInfo;

    // Try to get detailed spend logs (last 30 days)
    let logs: any[] = [];
    try {
      const endDate = new Date().toISOString().split("T")[0];
      const startDate = new Date(Date.now() - 30 * 86400000).toISOString().split("T")[0];
      const logsRes = await fetch(
        `${baseUrl}/spend/logs?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&api_key=${encodeURIComponent(apiKey)}`,
        { headers: { "Authorization": `Bearer ${apiKey}` } }
      );
      if (logsRes.ok) {
        const body = await logsRes.json();
        logs = Array.isArray(body) ? body : [];
      }
    } catch {
      // Detailed logs may not be available
    }

    // Aggregate from key info
    const totalSpend = info.spend || 0;
    const maxBudget = info.max_budget ?? null;
    const modelSpend: Record<string, number> = info.model_spend || {};
    const keyName = info.key_name || info.key_alias || "";
    const budgetDuration = info.budget_duration || null;
    const budgetResetAt = info.budget_reset_at || null;

    // Aggregate from detailed logs
    let totalPromptTokens = 0;
    let totalCompletionTokens = 0;
    const totalRequests = logs.length;
    const dailySpend: Record<string, number> = {};
    const modelBreakdown: Record<string, { requests: number; promptTokens: number; completionTokens: number; spend: number }> = {};

    for (const entry of logs) {
      totalPromptTokens += entry.prompt_tokens || 0;
      totalCompletionTokens += entry.completion_tokens || 0;
      const model = entry.model || "unknown";
      if (!modelBreakdown[model]) {
        modelBreakdown[model] = { requests: 0, promptTokens: 0, completionTokens: 0, spend: 0 };
      }
      modelBreakdown[model].requests++;
      modelBreakdown[model].promptTokens += entry.prompt_tokens || 0;
      modelBreakdown[model].completionTokens += entry.completion_tokens || 0;
      modelBreakdown[model].spend += entry.spend || 0;
      const day = (entry.startTime || entry.created_at || "").slice(0, 10);
      if (day) {
        dailySpend[day] = (dailySpend[day] || 0) + (entry.spend || 0);
      }
    }

    return {
      totalSpend,
      maxBudget,
      modelSpend,
      keyName,
      budgetDuration,
      budgetResetAt,
      totalPromptTokens,
      totalCompletionTokens,
      totalTokens: totalPromptTokens + totalCompletionTokens,
      totalRequests,
      modelBreakdown,
      dailySpend,
      hasDetailedLogs: logs.length > 0,
    };
  });

  // --- Settings ---
  ipcMain.handle("settings:get", () => settingsStore.store);
  ipcMain.handle("settings:set", (_event, key: string, value: any) => {
    settingsStore.set(key as any, value);
    if (key === 'autoStart') {
      app.setLoginItemSettings({ openAtLogin: !!value });
    }
  });

  // --- Window ---
  ipcMain.handle("window:minimize", () => mainWindow?.minimize());
  ipcMain.handle("window:maximize", () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow?.maximize();
    }
  });
  ipcMain.handle("window:close", () => mainWindow?.close());
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

app.whenReady().then(async () => {
  registerIpcHandlers();

  // Sync auto-start with OS
  app.setLoginItemSettings({ openAtLogin: settingsStore.get('autoStart') });

  mainWindow = createMainWindow();

  const trayCallbacks = {
    onShowWindow: () => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.show();
        mainWindow.focus();
      }
    },
    onRestartGateway: () => { stopGatewayProcess(); startGateway(); },
  };
  createTray(trayCallbacks);

  // Skill integrity check — must run BEFORE loading renderer so
  // pendingIntegrityResult is ready when App.vue calls the IPC.
  const integrityResult = verifySkillIntegrity();
  if (!integrityResult.snapshotExists) {
    console.log("No skill integrity snapshot found — generating baseline (installer may not have run)...");
    generateAndSignSnapshot();
  } else if (!integrityResult.valid) {
    console.log("Skill integrity check failed — changes detected");
    pendingIntegrityResult = integrityResult;
  }

  // Load the Vue renderer UI
  if (isDev) {
    // Poll until Vite dev server is ready (up to 60s)
    const waitForVite = async () => {
      for (let i = 0; i < 120; i++) {
        try {
          await mainWindow!.loadURL(VITE_DEV_URL);
          return; // success
        } catch {
          await new Promise((r) => setTimeout(r, 500));
        }
      }
      // Last attempt — let it throw naturally
      await mainWindow!.loadURL(VITE_DEV_URL);
    };
    await waitForVite();
  } else {
    await mainWindow.loadFile(
      path.join(__dirname, "../renderer/dist/index.html")
    );
  }

  // Watch skill directories for mid-session changes
  startSkillFileWatcher();

  startGateway().catch((err) => {
    console.error("Failed to start gateway:", err);
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  (app as any).isQuitting = true;
  gwClient?.stop();
  stopGatewayProcess();
});

app.on("activate", () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
  }
});
