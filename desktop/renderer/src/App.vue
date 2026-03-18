<template>
  <div class="app-layout">
    <Sidebar />
    <main class="main-content">
      <router-view />
    </main>
  </div>

  <!-- Integrity Alert Dialog (shown immediately on launch or mid-session) -->
  <el-dialog
    v-model="integrityDialogVisible"
    title="⚠️ 技能文件完整性检查"
    width="560"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
  >
    <div v-if="integrityResult && !integrityResult.signatureValid" style="color:#ff3b30; margin-bottom:16px; font-weight:bold">
      🚨 完整性清单本身已被篡改 — 签名验证失败
    </div>

    <div v-if="integrityResult?.signatureValid" style="margin-bottom:12px; color:#666">
      以下技能文件自上次启动后发生了变化：
    </div>

    <div v-if="modifiedChanges.length" style="margin-bottom:12px">
      <div style="font-weight:bold; color:#ff9500; margin-bottom:4px">已修改 ({{ modifiedChanges.length }})</div>
      <div v-for="c in modifiedChanges" :key="c.skill + c.file" style="font-size:13px; color:#555; padding-left:12px">
        · {{ c.source }}/{{ c.skill }}/{{ c.file }}
      </div>
    </div>

    <div v-if="addedChanges.length" style="margin-bottom:12px">
      <div style="font-weight:bold; color:#ff3b30; margin-bottom:4px">新增文件 ({{ addedChanges.length }})</div>
      <div v-for="c in addedChanges" :key="c.skill + c.file" style="font-size:13px; color:#555; padding-left:12px">
        · {{ c.source }}/{{ c.skill }}/{{ c.file }}
      </div>
    </div>

    <div v-if="removedChanges.length" style="margin-bottom:12px">
      <div style="font-weight:bold; color:#ff9500; margin-bottom:4px">已删除 ({{ removedChanges.length }})</div>
      <div v-for="c in removedChanges" :key="c.skill + c.file" style="font-size:13px; color:#555; padding-left:12px">
        · {{ c.source }}/{{ c.skill }}/{{ c.file }}
      </div>
    </div>

    <template #footer>
      <el-button @click="exitApp">退出</el-button>
      <el-button type="primary" :loading="integrityLoading" @click="trustIntegrityChanges">
        信任并继续
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { ElMessage } from "element-plus";
import Sidebar from "@/components/Sidebar.vue";
import { useGatewayStore } from "@/stores/gateway";
import { useChatStore } from "@/stores/chat";
import { useSessionStore } from "@/stores/sessions";
import { useTaskStore } from "@/stores/tasks";

const gateway = useGatewayStore();
const chatStore = useChatStore();
const sessionStore = useSessionStore();
const taskStore = useTaskStore();

// ── Integrity check state ──
const integrityDialogVisible = ref(false);
const integrityResult = ref<IntegrityResult | null>(null);
const integrityLoading = ref(false);

const modifiedChanges = computed(() =>
  integrityResult.value?.changes.filter(c => c.type === "modified") ?? []
);
const addedChanges = computed(() =>
  integrityResult.value?.changes.filter(c => c.type === "added") ?? []
);
const removedChanges = computed(() =>
  integrityResult.value?.changes.filter(c => c.type === "removed") ?? []
);

async function trustIntegrityChanges() {
  integrityLoading.value = true;
  try {
    await window.openclaw.skills.acceptIntegrityChanges();
    integrityDialogVisible.value = false;
    integrityResult.value = null;
    ElMessage.success("已信任变更，完整性快照已更新");
  } catch (err: any) {
    ElMessage.error("更新快照失败: " + (err.message || err));
  } finally {
    integrityLoading.value = false;
  }
}

function exitApp() {
  window.close();
}

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
let unsubIntegrityAlert: (() => void) | null = null;

onMounted(async () => {
  // ── Integrity check (runs before anything else) ──
  try {
    const pending = await window.openclaw.skills.pendingIntegrityResult();
    if (pending && !pending.valid) {
      integrityResult.value = pending;
      integrityDialogVisible.value = true;
    }
  } catch {}

  // Listen for mid-session integrity alerts (file watcher)
  unsubIntegrityAlert = window.openclaw.skills.onIntegrityAlert((result) => {
    if (!result.valid) {
      integrityResult.value = result;
      integrityDialogVisible.value = true;
    }
  });

  // Gateway process status
  unsubStatus = window.openclaw.gateway.onStatus((status) => {
    gateway.status = status;
    if (status === "running") {
      window.openclaw.gateway.getPort().then((p) => (gateway.port = p));
    }
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
  unsubIntegrityAlert?.();
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
