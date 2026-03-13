<template>
  <div class="chat-view">
    <!-- Chat header -->
    <div class="chat-header">
      <div class="chat-header__left">
        <span class="chat-title">{{ currentAgent?.name || "选择一个智能体" }}</span>
        <span class="chat-session-key" v-if="chatStore.sessionKey">{{ chatStore.sessionKey }}</span>
      </div>
      <div class="chat-header__right">
        <button class="header-btn" @click="createNewChat" title="新对话">
          + 新对话
        </button>
      </div>
    </div>

    <!-- Chat thread -->
    <div class="chat-thread" ref="threadRef" @scroll="handleScroll">
      <!-- Loading -->
      <div v-if="chatStore.loading" class="chat-empty">
        <div class="chat-empty__hint">加载中…</div>
      </div>

      <!-- Empty state -->
      <div v-else-if="chatStore.messages.length === 0 && !chatStore.streaming" class="chat-empty">
        <div class="chat-empty__title">OpenClaw</div>
        <div class="chat-empty__hint">选择一个智能体，开始对话</div>
      </div>

      <!-- Grouped messages -->
      <template v-for="group in groupedMessages" :key="group.key">
        <div class="chat-group" :class="group.normalizedRole">
          <div class="chat-avatar" :class="group.normalizedRole">
            {{ group.normalizedRole === 'user' ? '我' : 'AI' }}
          </div>
          <div class="chat-group-messages">
            <div
              v-for="(msg, idx) in group.messages"
              :key="group.key + '-' + idx"
              class="chat-bubble"
              :class="{ 'has-copy': group.normalizedRole === 'assistant' }"
            >
              <button
                v-if="group.normalizedRole === 'assistant'"
                class="chat-copy-btn"
                @click="copyMessage(getMessageText(msg))"
                :title="copyTooltip"
              >
                {{ justCopied ? '✓' : '⎘' }}
              </button>
              <div
                v-if="group.normalizedRole === 'assistant'"
                class="chat-text"
                v-html="renderMarkdown(getMessageText(msg))"
              ></div>
              <div v-else class="chat-text chat-text--user">
                {{ getMessageText(msg) }}
              </div>
            </div>
            <div class="chat-group-footer">
              <span class="chat-sender-name">{{ group.normalizedRole === 'user' ? '我' : (currentAgent?.name || 'AI') }}</span>
              <span class="chat-group-timestamp">{{ formatTime(group.timestamp) }}</span>
            </div>
          </div>
        </div>
      </template>

      <!-- Streaming group -->
      <div v-if="chatStore.streaming" class="chat-group assistant">
        <div class="chat-avatar assistant">AI</div>
        <div class="chat-group-messages">
          <div class="chat-bubble streaming" v-if="chatStore.streamText">
            <div class="chat-text" v-html="renderMarkdown(chatStore.streamText)"></div>
          </div>
          <div v-else class="chat-bubble chat-reading-indicator">
            <span class="chat-reading-dots">
              <span></span><span></span><span></span>
            </span>
          </div>
          <div class="chat-group-footer">
            <span class="chat-sender-name">{{ currentAgent?.name || 'AI' }}</span>
            <span class="chat-group-timestamp">{{ formatTime(chatStore.streamStartedAt || Date.now()) }}</span>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="chatStore.lastError" class="chat-error">{{ chatStore.lastError }}</div>
    </div>

    <!-- New messages indicator -->
    <button v-if="showNewMessages" class="chat-new-messages" @click="scrollToBottom">
      新消息 ↓
    </button>

    <!-- Compose area -->
    <div class="chat-compose">
      <div class="chat-compose__row">
        <textarea
          ref="inputRef"
          v-model="inputText"
          :placeholder="composePlaceholder"
          @keydown="handleKeydown"
          @input="autoResize"
          rows="1"
          :disabled="!chatStore.wsConnected"
        ></textarea>
        <div class="chat-compose__actions">
          <button
            v-if="chatStore.streaming"
            class="compose-btn compose-btn--stop"
            @click="handleAbort"
            title="停止生成"
          >
            停止
          </button>
          <button
            v-else
            class="compose-btn compose-btn--send"
            @click="handleSend"
            :disabled="!inputText.trim() || !chatStore.wsConnected"
            title="发送"
          >
            发送<kbd class="btn-kbd">↵</kbd>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue";
import { useRoute } from "vue-router";
import { useChatStore } from "@/stores/chat";
import { useAgentStore } from "@/stores/agents";
import { renderMarkdown } from "@/utils/markdown";

const route = useRoute();
const chatStore = useChatStore();
const agentStore = useAgentStore();

const inputText = ref("");
const inputRef = ref<HTMLTextAreaElement>();
const threadRef = ref<HTMLDivElement>();
const showNewMessages = ref(false);
const justCopied = ref(false);
let isUserScrolledUp = false;

const currentAgent = computed(() => {
  const agentId = (route.params.agentId as string) || agentStore.currentAgentId;
  return agentStore.agents.find((a) => a.id === agentId);
});

const composePlaceholder = computed(() =>
  chatStore.wsConnected
    ? "输入消息 (↩ 发送, Shift+↩ 换行)"
    : "等待 Gateway 连接…"
);

const copyTooltip = computed(() => (justCopied.value ? "已复制" : "复制"));

// ── Extract text from a message (string content or content-block array) ──
function getMessageText(msg: unknown): string {
  return chatStore.extractText(msg) || "";
}

// ── Normalize role for display ──
function normalizeRole(role: string): string {
  const lower = role.toLowerCase();
  if (lower === "user") return "user";
  if (lower === "assistant") return "assistant";
  return "assistant"; // system / tool results shown as assistant
}

// ── Group consecutive messages by role ──
interface MessageGroup {
  key: string;
  normalizedRole: string;
  messages: unknown[];
  timestamp: number;
}

const groupedMessages = computed<MessageGroup[]>(() => {
  const msgs = chatStore.messages;
  if (!msgs || msgs.length === 0) return [];

  const groups: MessageGroup[] = [];
  let current: MessageGroup | null = null;

  for (let i = 0; i < msgs.length; i++) {
    const msg = msgs[i] as Record<string, unknown>;
    const role = normalizeRole(typeof msg.role === "string" ? msg.role : "assistant");
    const ts = typeof msg.timestamp === "number" ? msg.timestamp : Date.now();

    if (!current || current.normalizedRole !== role) {
      current = {
        key: `group-${i}`,
        normalizedRole: role,
        messages: [msg],
        timestamp: ts,
      };
      groups.push(current);
    } else {
      current.messages.push(msg);
    }
  }
  return groups;
});

// ── Auto-scroll ──
watch(
  () => [chatStore.messages.length, chatStore.streamText],
  () => {
    if (!isUserScrolledUp) {
      nextTick(scrollToBottom);
    } else {
      showNewMessages.value = true;
    }
  }
);

function handleScroll() {
  const el = threadRef.value;
  if (!el) return;
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  isUserScrolledUp = !atBottom;
  if (atBottom) showNewMessages.value = false;
}

function scrollToBottom() {
  const el = threadRef.value;
  if (el) el.scrollTop = el.scrollHeight;
  showNewMessages.value = false;
  isUserScrolledUp = false;
}

function autoResize() {
  nextTick(() => {
    const el = inputRef.value;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 150) + "px";
    }
  });
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    handleSend();
  }
}

async function copyMessage(content: string) {
  try {
    await navigator.clipboard.writeText(content);
    justCopied.value = true;
    setTimeout(() => (justCopied.value = false), 1500);
  } catch {
    // Clipboard not available
  }
}

async function handleSend() {
  const text = inputText.value.trim();
  if (!text || !chatStore.wsConnected) return;
  inputText.value = "";
  autoResize();
  await chatStore.sendMessage(text);
}

async function handleAbort() {
  await chatStore.abort();
}

function createNewChat() {
  chatStore.newSession();
}
</script>

<style scoped>
.chat-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  overflow: hidden;
}

/* ── Header ── */
.chat-header {
  height: 48px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.chat-header__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.chat-session-key {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 4px;
}

.chat-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-btn {
  padding: 4px 12px;
  font-size: 12px;
  color: var(--accent);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.header-btn:hover:not(:disabled) {
  background: var(--accent-subtle);
  border-color: var(--accent);
}

.header-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Thread ── */
.chat-thread {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px 16px;
  min-height: 0;
}

/* ── Empty state ── */
.chat-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding-bottom: 60px;
}

.chat-empty__title {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: -0.02em;
}

.chat-empty__hint {
  font-size: 13px;
  color: var(--text-muted);
}

/* ── Chat Group (Slack-style) ── */
.chat-group {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 16px;
  margin-left: 4px;
  margin-right: 16px;
}

.chat-group.user {
  flex-direction: row-reverse;
  justify-content: flex-start;
}

.chat-group-messages {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: min(720px, calc(100% - 60px));
}

.chat-group.user .chat-group-messages {
  align-items: flex-end;
}

.chat-group.user .chat-group-footer {
  justify-content: flex-end;
}

/* ── Avatar ── */
.chat-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
  align-self: flex-end;
  margin-bottom: 4px;
}

.chat-avatar.user {
  background: var(--accent-subtle);
  color: var(--accent);
}

.chat-avatar.assistant {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

/* ── Bubble ── */
.chat-bubble {
  position: relative;
  display: inline-block;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 10px 14px;
  max-width: 100%;
  word-wrap: break-word;
  transition: border-color 0.15s;
}

.chat-bubble.has-copy {
  padding-right: 36px;
}

.chat-group.user .chat-bubble {
  background: var(--msg-user-bg);
  color: var(--msg-user-text);
  border-color: var(--msg-user-bg);
  border-radius: 12px 4px 12px 12px;
}

.chat-bubble.streaming {
  border-color: var(--accent);
  border-style: solid;
}

/* ── Copy button ── */
.chat-copy-btn {
  position: absolute;
  top: 6px;
  right: 8px;
  border: 1px solid var(--border);
  background: var(--bg-primary);
  color: var(--text-muted);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s;
}

.chat-bubble:hover .chat-copy-btn {
  opacity: 1;
  pointer-events: auto;
}

.chat-copy-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* ── Group footer (name + time) ── */
.chat-group-footer {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-top: 4px;
}

.chat-sender-name {
  font-weight: 500;
  font-size: 11px;
  color: var(--text-muted);
}

.chat-group-timestamp {
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0.7;
}

/* ── Chat text / Markdown ── */
.chat-text {
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: break-word;
  color: var(--text-primary);
}

.chat-text--user {
  white-space: pre-wrap;
}

.chat-group.user .chat-text {
  color: var(--msg-user-text);
}

.chat-text :deep(p) {
  margin: 0;
}

.chat-text :deep(p + p) {
  margin-top: 0.6em;
}

.chat-text :deep(ul),
.chat-text :deep(ol) {
  padding-left: 1.5em;
  margin: 4px 0 8px;
}

.chat-text :deep(li + li) {
  margin-top: 0.25em;
}

.chat-text :deep(a) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.chat-text :deep(code) {
  font-family: "Cascadia Code", "Fira Code", Consolas, monospace;
  font-size: 0.9em;
}

.chat-text :deep(:not(pre) > code) {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  padding: 1px 5px;
  border-radius: 3px;
}

.chat-text :deep(pre) {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  margin: 8px 0;
  overflow-x: auto;
}

.chat-text :deep(pre code) {
  padding: 0;
  background: transparent;
  border: none;
}

.chat-text :deep(blockquote) {
  border-left: 3px solid var(--accent);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--text-secondary);
}

.chat-text :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}

.chat-text :deep(th),
.chat-text :deep(td) {
  border: 1px solid var(--border);
  padding: 5px 10px;
}

.chat-text :deep(th) {
  background: var(--bg-tertiary);
  font-weight: 600;
}

.chat-text :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1em 0;
}

/* ── Reading indicator (typing dots) ── */
.chat-reading-indicator {
  padding: 10px 16px;
}

.chat-reading-dots {
  display: inline-flex;
  gap: 5px;
  align-items: center;
}

.chat-reading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: chat-dot-wave 1.4s ease-in-out infinite;
}

.chat-reading-dots span:nth-child(2) {
  animation-delay: 0.18s;
}

.chat-reading-dots span:nth-child(3) {
  animation-delay: 0.36s;
}

@keyframes chat-dot-wave {
  0%, 60%, 100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-4px);
  }
}

/* ── Error ── */
.chat-error {
  margin: 8px 16px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 59, 48, 0.08);
  color: var(--danger);
  font-size: 13px;
  border: 1px solid rgba(255, 59, 48, 0.2);
}

/* ── New messages indicator ── */
.chat-new-messages {
  align-self: center;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  margin: 0 auto;
  font-size: 12px;
  color: var(--text-primary);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 999px;
  cursor: pointer;
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.15s;
}

.chat-new-messages:hover {
  border-color: var(--accent);
  background: var(--accent-subtle);
}

/* ── Compose ── */
.chat-compose {
  flex-shrink: 0;
  padding: 10px 20px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}

.chat-compose__row {
  display: flex;
  align-items: stretch;
  gap: 10px;
}

.chat-compose__row textarea {
  flex: 1;
  height: 40px;
  min-height: 40px;
  max-height: 150px;
  padding: 9px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  line-height: 1.45;
  resize: none;
  outline: none;
  overflow-y: auto;
  transition: border-color 0.15s;
}

.chat-compose__row textarea:focus {
  border-color: var(--accent);
}

.chat-compose__row textarea::placeholder {
  color: var(--text-muted);
}

.chat-compose__row textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chat-compose__actions {
  flex-shrink: 0;
  display: flex;
  align-items: stretch;
  gap: 8px;
}

.compose-btn {
  padding: 0 16px;
  height: 40px;
  font-size: 13px;
  font-family: inherit;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  transition: all 0.12s;
}

.compose-btn--send {
  background: var(--accent);
  color: #fff;
}

.compose-btn--send:hover:not(:disabled) {
  background: var(--accent-hover);
}

.compose-btn--send:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.compose-btn--stop {
  background: var(--bg-tertiary);
  color: var(--danger);
  border: 1px solid var(--border);
}

.compose-btn--stop:hover {
  border-color: var(--danger);
}

.btn-kbd {
  font-size: 10px;
  opacity: 0.6;
  margin-left: 2px;
  padding: 1px 4px;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 3px;
  font-family: inherit;
  background: transparent;
  color: inherit;
}
</style>
