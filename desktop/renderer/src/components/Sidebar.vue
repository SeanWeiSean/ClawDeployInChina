<template>
  <aside class="sidebar">
    <!-- Tab switcher (Apple segmented control) -->
    <div class="sidebar-tabs">
      <div class="segmented-control">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="segment-btn"
          :class="{ active: activeTab === tab.id }"
          @click="switchTab(tab.id)"
          :title="tab.label"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <!-- Tab content -->
    <div class="sidebar-content">
      <!-- Sessions tab (default) -->
      <div v-if="activeTab === 'sessions'" class="tab-panel">
        <div class="session-list">
          <div
            v-for="s in sessionStore.sortedSessions"
            :key="s.key"
            class="session-card"
            :class="{ active: chatStore.sessionKey === s.key }"
            @click="selectSession(s.key)"
          >
            <div class="session-avatar">{{ s.title.charAt(0) }}</div>
            <div class="session-info">
              <div class="session-name">{{ s.title }}</div>
              <div class="session-preview">{{ s.preview || '暂无消息' }}</div>
            </div>
            <button
              class="session-delete-btn"
              @click.stop="deleteSession(s.key)"
              title="删除会话"
            >&times;</button>
          </div>
          <div v-if="sessionStore.sessions.length === 0" class="empty-hint">
            点击上方按钮开始新对话
          </div>
        </div>
      </div>

      <!-- IM Channels tab -->
      <div v-if="activeTab === 'channels'" class="tab-panel">
        <div class="channel-list">
          <div
            v-for="ch in channelStore.channels"
            :key="ch.id"
            class="list-item"
            @click="router.push('/channels')"
          >
            <span class="item-icon">{{ ch.icon }}</span>
            <span class="item-name">{{ ch.name }}</span>
            <span class="status-dot" :class="ch.connected ? 'online' : 'offline'"></span>
          </div>
          <div v-if="channelStore.channels.length === 0" class="empty-hint">
            暂无消息频道
          </div>
        </div>
      </div>

      <!-- Tasks tab -->
      <div v-if="activeTab === 'tasks'" class="tab-panel">
        <div class="task-list">
          <div
            v-for="task in taskStore.tasks"
            :key="task.id"
            class="list-item"
            @click="router.push('/tasks')"
          >
            <span class="item-icon item-icon-text">时</span>
            <span class="item-name">{{ task.name }}</span>
            <span class="status-dot" :class="task.enabled ? 'online' : 'offline'"></span>
          </div>
          <div v-if="taskStore.tasks.length === 0" class="empty-hint">
            暂无定时任务
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom: Gateway status + Settings -->
    <div class="sidebar-footer">
      <div class="gateway-status" :class="gatewayStatusClass">
        <span class="status-indicator"></span>
        <span class="status-text">{{ gatewayStatusLabel }}</span>
      </div>
      <button class="settings-btn" @click="router.push('/settings')" title="设置">
        <span class="settings-icon">设置</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useAgentStore } from "@/stores/agents";
import { useChannelStore } from "@/stores/channels";
import { useTaskStore } from "@/stores/tasks";
import { useGatewayStore } from "@/stores/gateway";
import { useChatStore } from "@/stores/chat";
import { useSessionStore } from "@/stores/sessions";

const router = useRouter();
const agentStore = useAgentStore();
const channelStore = useChannelStore();
const taskStore = useTaskStore();
const gateway = useGatewayStore();
const chatStore = useChatStore();
const sessionStore = useSessionStore();

const tabs = [
  { id: "sessions", icon: "对", label: "对话" },
  { id: "channels", icon: "频", label: "消息频道" },
  { id: "tasks", icon: "时", label: "定时任务" },
];

const activeTab = ref("sessions");

function switchTab(tabId: string) {
  activeTab.value = tabId;
  if (tabId === "channels") router.push("/channels");
  else if (tabId === "tasks") router.push("/tasks");
}

const gatewayStatusClass = computed(() => ({
  running: gateway.status === "running",
  starting: gateway.status === "starting" || gateway.status === "restarting",
  failed: gateway.status === "failed" || gateway.status === "timeout",
}));

const gatewayStatusLabel = computed(() => {
  const labels: Record<string, string> = {
    stopped: "网关已停止",
    starting: "网关启动中...",
    running: "网关运行中",
    restarting: "网关重启中...",
    failed: "网关连接失败",
    stopping: "网关停止中...",
    timeout: "网关连接超时",
  };
  return labels[gateway.status] || `网关: ${gateway.status}`;
});

function selectAgent(agentId: string) {
  agentStore.currentAgentId = agentId;
  router.push(`/chat/${agentId}`);
}

function selectSession(key: string) {
  chatStore.switchSession(key);
  router.push("/chat");
}

function createNewSession() {
  chatStore.newSession();
  router.push("/chat");
}

function deleteSession(key: string) {
  sessionStore.removeSession(key);
  // If deleting the current session, create a new one
  if (chatStore.sessionKey === key) {
    if (sessionStore.sessions.length > 0) {
      chatStore.switchSession(sessionStore.sortedSessions[0].key);
    } else {
      chatStore.newSession();
    }
  }
}
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  height: 100vh;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  user-select: none;
}

/* Tab bar — Apple segmented control */
.sidebar-tabs {
  padding: 14px 14px 10px;
}

.segmented-control {
  display: flex;
  background: var(--bg-primary);
  border-radius: 9px;
  padding: 3px;
  gap: 2px;
}

.segment-btn {
  flex: 1;
  padding: 7px 8px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.segment-btn:hover {
  color: var(--text-primary);
}

.segment-btn.active {
  background: var(--bg-secondary);
  color: var(--text-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
  font-weight: 600;
}

/* Session list header */
.session-list-header {
  padding: 10px 14px 6px;
  display: flex;
  justify-content: flex-end;
}

.new-session-btn {
  padding: 5px 12px;
  border: none;
  border-radius: 6px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: opacity 0.15s;
}

.new-session-btn:hover {
  opacity: 0.85;
}

.session-list {
  flex: 1;
  overflow-y: auto;
}

.session-delete-btn {
  display: none;
  padding: 0 4px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
  line-height: 1;
  flex-shrink: 0;
}

.session-delete-btn:hover {
  color: var(--danger);
  background: var(--bg-tertiary);
}

.session-card:hover .session-delete-btn {
  display: block;
}

/* Content */
.sidebar-content {
  flex: 1;
  overflow-y: auto;
}

.tab-panel {
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 16px 14px 6px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* List items */
.list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px 8px 14px;
  cursor: pointer;
  transition: background 0.12s;
  color: var(--text-secondary);
  border-left: 2px solid transparent;
  font-size: 13px;
}

.list-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.list-item.active {
  background: var(--accent-subtle);
  color: var(--accent);
  border-left-color: var(--accent);
}

.item-icon {
  font-size: 14px;
  flex-shrink: 0;
  width: 20px;
  text-align: center;
  color: var(--text-muted);
}

.list-item.active .item-icon {
  color: var(--accent);
}

.item-icon-text {
  font-size: 11px;
  font-weight: 600;
}

.item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Status dot */
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.online {
  background: var(--success);
}

.status-dot.offline {
  background: var(--border);
}

.empty-hint {
  padding: 24px 14px;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

/* Session card — WeChat style */
.session-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  cursor: pointer;
  transition: background 0.12s;
  border-bottom: 1px solid var(--border-row);
}

.session-card:hover {
  background: var(--bg-tertiary);
}

.session-card.active {
  background: var(--accent-subtle);
}

.session-avatar {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}

.session-card.active .session-avatar {
  background: var(--accent);
  color: #fff;
}

.session-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.session-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-preview {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Footer: gateway + settings */
.sidebar-footer {
  border-top: 1px solid var(--border);
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.gateway-status {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
}

.gateway-status .status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--border);
  flex-shrink: 0;
}

.gateway-status.running {
  color: var(--text-secondary);
}

.gateway-status.running .status-indicator {
  background: var(--success);
}

.gateway-status.starting .status-indicator {
  background: var(--warning);
  animation: pulse 1.2s ease-in-out infinite;
}

.gateway-status.failed .status-indicator {
  background: var(--danger);
}

.status-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.settings-btn {
  padding: 5px 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 5px;
  font-size: 14px;
  color: var(--text-muted);
  transition: background 0.12s, color 0.12s;
  flex-shrink: 0;
}

.settings-icon {
  font-size: 12px;
}

.settings-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
</style>
