<template>
  <div class="app-layout">
    <Sidebar />
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import Sidebar from "@/components/Sidebar.vue";
import { useGatewayStore } from "@/stores/gateway";
import { useChatStore } from "@/stores/chat";
import { useSessionStore } from "@/stores/sessions";
import { useTaskStore } from "@/stores/tasks";

const gateway = useGatewayStore();
const chatStore = useChatStore();
const sessionStore = useSessionStore();
const taskStore = useTaskStore();

function applyTheme(mode: string) {
  const html = document.documentElement;
  html.classList.remove("light", "dark");
  if (mode === "system") {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    html.classList.add(prefersDark ? "dark" : "light");
  } else {
    html.classList.add(mode);
  }
}

let unsubStatus: (() => void) | null = null;
let unsubLog: (() => void) | null = null;
let unsubWsConnected: (() => void) | null = null;
let unsubWsDisconnected: (() => void) | null = null;
let unsubChatEvent: (() => void) | null = null;

onMounted(() => {
  // Gateway process status
  unsubStatus = window.openclaw.gateway.onStatus((status) => {
    gateway.status = status;
  });
  unsubLog = window.openclaw.gateway.onLog((msg) => {
    gateway.addLog(msg);
  });

  // WebSocket connection status
  unsubWsConnected = window.openclaw.gateway.onWsConnected((mainSessionKey) => {
    chatStore.wsConnected = true;
    // Apply the canonical session key from gateway hello
    if (mainSessionKey) {
      chatStore.sessionKey = mainSessionKey;
      chatStore.resolvedSessionKey = mainSessionKey;
    }
    // Register in session store
    sessionStore.ensureSession(chatStore.sessionKey);
    chatStore.loadHistory();
    // Fetch scheduled tasks now that gateway is connected
    taskStore.fetchTasks();
  });
  unsubWsDisconnected = window.openclaw.gateway.onWsDisconnected(() => {
    chatStore.wsConnected = false;
  });

  // Chat events (delta, final, aborted, error)
  unsubChatEvent = window.openclaw.chat.onEvent((payload) => {
    chatStore.handleChatEvent(payload);
  });

  // Get initial status
  window.openclaw.gateway.getStatus().then((s) => (gateway.status = s));
  window.openclaw.gateway.getPort().then((p) => (gateway.port = p));
  window.openclaw.chat.isConnected().then((c) => {
    chatStore.wsConnected = c;
    if (c) chatStore.loadHistory();
  });

  // Apply persisted theme and accent color
  window.openclaw.settings.get().then((s) => {
    applyTheme(s.themeMode || "light");
    if (s.accentColor) {
      document.documentElement.style.setProperty("--accent", s.accentColor);
    }
  });

  // React to OS theme changes when in "system" mode
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    window.openclaw.settings.get().then((s) => {
      if (s.themeMode === "system") applyTheme("system");
    });
  });
});

onUnmounted(() => {
  unsubStatus?.();
  unsubLog?.();
  unsubWsConnected?.();
  unsubWsDisconnected?.();
  unsubChatEvent?.();
});
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.main-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
