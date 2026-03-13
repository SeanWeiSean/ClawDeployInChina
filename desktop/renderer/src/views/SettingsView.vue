<template>
  <div class="settings-view">
    <!-- Left sidebar: icon grid nav -->
    <div class="settings-sidebar">
      <div class="settings-title">
        <button class="back-btn" @click="router.back()" title="返回">←</button>
        设置
      </div>
      <div class="menu-list">
        <div
          v-for="item in menuItems"
          :key="item.id"
          class="settings-menu-item"
          :class="{ active: activeSection === item.id }"
          @click="activeSection = item.id"
        >
          <span class="menu-icon" :style="{ background: item.color }" v-html="item.svg"></span>
          <span class="menu-label">{{ item.label }}</span>
        </div>
      </div>
    </div>

    <!-- Right content: grouped card rows -->
    <div class="settings-content">
      <!-- General -->
      <div v-if="activeSection === 'general'" class="section">
        <div class="section-label">通用</div>
        <div class="card-group">
          <div class="card-row">
            <span class="row-label">语言</span>
            <el-select v-model="settings.language" size="small" style="width: 140px">
              <el-option label="简体中文" value="zh-CN" />
              <el-option label="English" value="en" />
            </el-select>
          </div>
          <div class="card-row">
            <span class="row-label">开机自启</span>
            <el-switch v-model="settings.autoStart" />
          </div>
          <div class="card-row no-border">
            <span class="row-label">启动时最小化到托盘</span>
            <el-switch v-model="settings.startMinimized" />
          </div>
        </div>
      </div>

      <!-- Theme -->
      <div v-if="activeSection === 'theme'" class="section">
        <div class="section-label">外观</div>
        <div class="card-group">
          <div class="card-row">
            <span class="row-label">主题模式</span>
            <el-radio-group v-model="settings.themeMode" size="small">
              <el-radio value="light">浅色</el-radio>
              <el-radio value="dark">深色</el-radio>
              <el-radio value="system">跟随系统</el-radio>
            </el-radio-group>
          </div>
          <div class="card-row no-border">
            <span class="row-label">强调色</span>
            <el-color-picker v-model="settings.accentColor" size="small" />
          </div>
        </div>
      </div>

      <!-- Usage -->
      <div v-if="activeSection === 'usage'" class="section">
        <div class="section-label">用量</div>

        <!-- Loading / Error states -->
        <div v-if="usageLoading" class="card-group">
          <div class="card-row no-border placeholder-row">
            <span class="placeholder-text">正在加载用量数据…</span>
          </div>
        </div>
        <div v-else-if="usageError" class="card-group">
          <div class="card-row no-border placeholder-row">
            <span class="placeholder-text" style="color: var(--text-muted)">{{ usageError }}</span>
          </div>
          <div class="card-row no-border" style="justify-content: center; padding-top: 0">
            <el-button size="small" @click="loadUsage">重试</el-button>
          </div>
        </div>

        <!-- Data loaded -->
        <template v-else-if="usageData">
          <!-- Spend overview -->
          <div class="card-group">
            <div class="card-row" :class="{ 'no-border': !usageData.maxBudget }">
              <span class="row-label">总花费</span>
              <span class="row-value usage-spend">${{ usageData.totalSpend.toFixed(4) }}</span>
            </div>
            <div v-if="usageData.maxBudget" class="card-row no-border">
              <span class="row-label">预算</span>
              <div class="budget-bar-wrapper">
                <span class="row-value">${{ usageData.totalSpend.toFixed(2) }} / ${{ usageData.maxBudget.toFixed(2) }}</span>
                <div class="budget-bar">
                  <div class="budget-bar-fill" :style="{ width: Math.min(100, (usageData.totalSpend / usageData.maxBudget) * 100) + '%' }"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Token usage (from detailed logs) -->
          <template v-if="usageData.hasDetailedLogs">
            <div class="sub-label">Token 用量（近 30 天）</div>
            <div class="card-group">
              <div class="card-row">
                <span class="row-label">API 调用次数</span>
                <span class="row-value">{{ usageData.totalRequests.toLocaleString() }}</span>
              </div>
              <div class="card-row">
                <span class="row-label">输入 Tokens</span>
                <span class="row-value">{{ usageData.totalPromptTokens.toLocaleString() }}</span>
              </div>
              <div class="card-row">
                <span class="row-label">输出 Tokens</span>
                <span class="row-value">{{ usageData.totalCompletionTokens.toLocaleString() }}</span>
              </div>
              <div class="card-row no-border">
                <span class="row-label">总 Tokens</span>
                <span class="row-value">{{ usageData.totalTokens.toLocaleString() }}</span>
              </div>
            </div>
          </template>

          <!-- Per-model breakdown -->
          <template v-if="usageModelList.length">
            <div class="sub-label">模型用量明细</div>
            <div class="card-group">
              <div
                v-for="(m, idx) in usageModelList"
                :key="m.name"
                class="card-row"
                :class="{ 'no-border': idx === usageModelList.length - 1 }"
              >
                <div class="model-usage-info">
                  <span class="row-label">{{ m.name }}</span>
                  <span class="row-sub" v-if="m.requests">{{ m.requests }} 次调用 · {{ m.promptTokens.toLocaleString() }} 输入 · {{ m.completionTokens.toLocaleString() }} 输出</span>
                </div>
                <span class="row-value usage-spend">${{ m.spend.toFixed(4) }}</span>
              </div>
            </div>
          </template>

          <!-- Key info -->
          <template v-if="usageData.keyName || usageData.budgetDuration">
            <div class="sub-label">Key 信息</div>
            <div class="card-group">
              <div v-if="usageData.keyName" class="card-row" :class="{ 'no-border': !usageData.budgetDuration }">
                <span class="row-label">Key 名称</span>
                <span class="row-value">{{ usageData.keyName }}</span>
              </div>
              <div v-if="usageData.budgetDuration" class="card-row" :class="{ 'no-border': !usageData.budgetResetAt }">
                <span class="row-label">预算周期</span>
                <span class="row-value">{{ usageData.budgetDuration }}</span>
              </div>
              <div v-if="usageData.budgetResetAt" class="card-row no-border">
                <span class="row-label">预算重置时间</span>
                <span class="row-value">{{ new Date(usageData.budgetResetAt).toLocaleString() }}</span>
              </div>
            </div>
          </template>

          <div class="section-actions">
            <el-button size="small" @click="loadUsage" :loading="usageLoading">刷新</el-button>
          </div>
        </template>

        <div class="section-footer">数据来源于 LiteLLM Proxy，需要 Gateway 运行中。</div>
      </div>

      <!-- Models & API -->
      <div v-if="activeSection === 'models'" class="section">
        <div class="section-header">
          <div class="section-header-title">Models & API</div>
          <el-button size="small" @click="reconnectGateway">Reconnect</el-button>
        </div>

        <!-- Custom Models -->
        <div class="sub-label-row">
          <span class="sub-label" style="margin-bottom:0">Custom Models</span>
          <el-button size="small" @click="showAddModel = true">Add Custom Model</el-button>
        </div>
        <div class="card-group">
          <template v-if="customModels.length">
            <div
              v-for="(m, idx) in customModels"
              :key="m.id"
              class="card-row"
              :class="{ 'no-border': idx === customModels.length - 1 }"
            >
              <div class="custom-model-info">
                <span class="row-label">{{ m.name }}</span>
                <span class="row-sub">{{ m.baseUrl }} · {{ m.apiFormat === 'anthropic' ? 'Anthropic' : 'OpenAI' }}</span>
              </div>
              <div class="custom-model-actions">
                <span v-if="m.id === selectedModel" class="badge badge-green">Current Selection</span>
                <el-button v-else size="small" @click="selectModel(m.id)">Select</el-button>
                <el-button size="small" @click="editCustomModel(idx)">Edit</el-button>
                <el-button size="small" type="danger" plain @click="removeCustomModel(idx)">Delete</el-button>
              </div>
            </div>
          </template>
          <div v-else class="card-row no-border placeholder-row">
            <span class="placeholder-text">No custom models yet</span>
          </div>
        </div>

        <!-- Add Custom Model dialog -->
        <el-dialog v-model="showAddModel" title="Add Custom Model" width="460px" :close-on-click-modal="false">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="Model Name">
              <el-input v-model="newModel.name" placeholder="e.g. my-gpt-4o" />
            </el-form-item>
            <el-form-item label="Base URL">
              <el-input v-model="newModel.baseUrl" placeholder="https://api.example.com/v1" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="newModel.apiKey" type="password" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item label="API Format">
              <el-radio-group v-model="newModel.apiFormat">
                <el-radio value="openai">Chat/Completion (OpenAI)</el-radio>
                <el-radio value="anthropic">Anthropic</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-form>
          <div class="test-result" v-if="testResult">
            <span :class="testResult.ok ? 'test-ok' : 'test-fail'">{{ testResult.message }}</span>
          </div>
          <template #footer>
            <div style="display:flex;justify-content:space-between;width:100%">
              <el-button :loading="testLoading" @click="testCustomModel">Test Connection</el-button>
              <div style="display:flex;gap:8px">
                <el-button @click="showAddModel = false">Cancel</el-button>
                <el-button type="primary" @click="addCustomModel">Add</el-button>
              </div>
            </div>
          </template>
        </el-dialog>

        <!-- Edit Custom Model dialog -->
        <el-dialog v-model="showEditModel" title="Edit Custom Model" width="460px" :close-on-click-modal="false">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="Model Name">
              <el-input v-model="editModel.name" placeholder="e.g. my-gpt-4o" />
            </el-form-item>
            <el-form-item label="Base URL">
              <el-input v-model="editModel.baseUrl" placeholder="https://api.example.com/v1" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="editModel.apiKey" type="password" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item label="API Format">
              <el-radio-group v-model="editModel.apiFormat">
                <el-radio value="openai">Chat/Completion (OpenAI)</el-radio>
                <el-radio value="anthropic">Anthropic</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-form>
          <div class="test-result" v-if="editTestResult">
            <span :class="editTestResult.ok ? 'test-ok' : 'test-fail'">{{ editTestResult.message }}</span>
          </div>
          <template #footer>
            <div style="display:flex;justify-content:space-between;width:100%">
              <el-button :loading="editTestLoading" @click="testEditModel">Test Connection</el-button>
              <div style="display:flex;gap:8px">
                <el-button @click="showEditModel = false">Cancel</el-button>
                <el-button type="primary" @click="saveEditModel">Save</el-button>
              </div>
            </div>
          </template>
        </el-dialog>

        <!-- Gateway URL -->
        <div class="sub-label-row" style="margin-top: 40px">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="sub-label" style="margin-bottom:0">Gateway URL</span>
            <span class="badge" :class="gateway.status === 'running' ? 'badge-green' : 'badge-red'">
              {{ gateway.status === 'running' ? 'Connected' : gateway.status }}
            </span>
          </div>
          <div style="display:flex;gap:8px">
            <el-button size="small" @click="reconnectGateway">Reconnect</el-button>
            <el-button size="small" type="danger" @click="resetConnection">Reset Connection</el-button>
          </div>
        </div>

        <!-- Port -->
        <div class="card-group" style="margin-top: 14px">
          <div class="card-row no-border port-row">
            <div class="port-info">
              <div class="port-title">Port</div>
              <div class="port-desc">Gateway will restart automatically after changing the port. If the default port is occupied, the system will try adjacent ports.</div>
            </div>
            <div class="port-input-group">
              <span class="port-prefix">ws://127.0.0.1 :</span>
              <el-input
                v-model="gatewayPort"
                size="small"
                style="width: 80px"
                @change="saveGatewayPort"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Skills -->
      <div v-if="activeSection === 'skills'" class="section">
        <div class="section-label">技能管理</div>

        <!-- Built-in Skills -->
        <div class="sub-label" style="margin-top:0">Built-in Skills ({{ builtinSkills.length }})</div>
        <div class="card-group">
          <template v-if="builtinSkills.length">
            <div
              v-for="(skill, idx) in builtinSkills"
              :key="skill.id"
              class="card-row"
              :class="{ 'no-border': idx === builtinSkills.length - 1 }"
            >
              <div class="skill-info">
                <span class="row-label">{{ skill.name }}</span>
                <span class="skill-desc">{{ skill.description }}</span>
              </div>
              <span class="badge badge-green">Built-in</span>
            </div>
          </template>
          <div v-else class="card-row no-border placeholder-row">
            <span class="placeholder-text">未检测到内置技能</span>
          </div>
        </div>

        <!-- Custom Skills -->
        <div class="sub-label">Custom Skills ({{ customSkills.length }})</div>
        <div class="card-group">
          <template v-if="customSkills.length">
            <div
              v-for="(skill, idx) in customSkills"
              :key="skill.id"
              class="card-row"
              :class="{ 'no-border': idx === customSkills.length - 1 }"
            >
              <div class="skill-info">
                <span class="row-label">{{ skill.name }}</span>
                <span class="skill-desc">{{ skill.description }}</span>
              </div>
              <span class="badge badge-blue">Custom</span>
            </div>
          </template>
          <div v-else class="card-row no-border placeholder-row">
            <span class="placeholder-text">暂无自定义技能</span>
          </div>
        </div>
      </div>

      <!-- Workspace -->
      <div v-if="activeSection === 'workspace'" class="section">
        <div class="section-label">工作区</div>
        <div class="card-group">
          <div class="card-row">
            <span class="row-label">数据目录</span>
            <span class="row-value">{{ stateDir }}</span>
          </div>
          <div class="card-row no-border">
            <span class="row-label">网关端口</span>
            <span class="row-value">{{ gateway.port }}</span>
          </div>
        </div>
      </div>

      <!-- Data & Privacy -->
      <div v-if="activeSection === 'privacy'" class="section">
        <div class="section-label">数据与隐私</div>
        <div class="card-group">
          <div class="card-row no-border">
            <span class="row-label">聊天记录</span>
            <el-button type="danger" plain size="small" @click="clearChatHistory">清除所有记录</el-button>
          </div>
        </div>
      </div>

      <!-- About -->
      <div v-if="activeSection === 'about'" class="section">
        <div class="section-label">关于</div>
        <div class="about-card">
          <div class="about-icon">🦞</div>
          <div class="about-name">MicroClaw</div>
          <div class="about-version">版本 1.0.0</div>
        </div>
        <div class="card-group" style="margin-top: 16px">
          <div class="card-row no-border">
            <span class="row-label">版权</span>
            <span class="row-value">© 2026 MicroClaw</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, computed } from "vue";
import { useRouter } from "vue-router";
import { useGatewayStore } from "@/stores/gateway";
import { useChatStore } from "@/stores/chat";
import { ElMessage, ElMessageBox } from "element-plus";

const router = useRouter();
const gateway = useGatewayStore();
const chatStore = useChatStore();

const activeSection = ref("general");
const stateDir = ref("");

const settings = reactive({
  language: "zh-CN",
  autoStart: false,
  startMinimized: false,
  themeMode: "light",
  accentColor: "#4a90d9",
});

// --- Models & API state ---
interface ModelEntry {
  id: string;
  name: string;
  baseUrl?: string;
  apiKey?: string;
  apiFormat?: 'openai' | 'anthropic';
}

const builtinModels = ref<ModelEntry[]>([
  { id: "MAI-01-Preview", name: "MAI-01-Preview" },
]);
const customModels = ref<ModelEntry[]>([]);
const selectedModel = ref("Pony-Alpha-2");
const gatewayPort = ref("18789");
const showAddModel = ref(false);
const newModel = reactive({ name: "", baseUrl: "", apiKey: "", apiFormat: "openai" as 'openai' | 'anthropic' });
const testLoading = ref(false);
const testResult = ref<{ ok: boolean; message: string } | null>(null);

const showEditModel = ref(false);
const editingIndex = ref(-1);
const editModel = reactive({ name: "", baseUrl: "", apiKey: "", apiFormat: "openai" as 'openai' | 'anthropic' });
const editTestLoading = ref(false);
const editTestResult = ref<{ ok: boolean; message: string } | null>(null);

const builtinSkills = ref<{ id: string; name: string; description: string }[]>([]);
const customSkills = ref<{ id: string; name: string; description: string }[]>([]);

// --- Usage state ---
interface UsageStats {
  totalSpend: number;
  maxBudget: number | null;
  modelSpend: Record<string, number>;
  keyName: string;
  budgetDuration: string | null;
  budgetResetAt: string | null;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  totalRequests: number;
  modelBreakdown: Record<string, { requests: number; promptTokens: number; completionTokens: number; spend: number }>;
  dailySpend: Record<string, number>;
  hasDetailedLogs: boolean;
}
const usageData = ref<UsageStats | null>(null);
const usageLoading = ref(false);
const usageError = ref("");

const usageModelList = computed(() => {
  if (!usageData.value) return [];
  // Use detailed breakdown if available, otherwise fall back to modelSpend
  if (usageData.value.hasDetailedLogs && Object.keys(usageData.value.modelBreakdown).length) {
    return Object.entries(usageData.value.modelBreakdown).map(([name, d]) => ({
      name,
      requests: d.requests,
      promptTokens: d.promptTokens,
      completionTokens: d.completionTokens,
      spend: d.spend,
    }));
  }
  return Object.entries(usageData.value.modelSpend).map(([name, spend]) => ({
    name,
    requests: 0,
    promptTokens: 0,
    completionTokens: 0,
    spend,
  }));
});

async function loadUsage() {
  usageLoading.value = true;
  usageError.value = "";
  try {
    usageData.value = await (window as any).openclaw.usage.getStats();
  } catch (err: any) {
    usageError.value = err.message || "获取用量数据失败";
    usageData.value = null;
  } finally {
    usageLoading.value = false;
  }
}

const svg = {
  general: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="2.5"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.22 4.22l1.42 1.42M14.36 14.36l1.42 1.42M4.22 15.78l1.42-1.42M14.36 5.64l1.42-1.42"/></svg>`,
  theme: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="7"/><path d="M10 3a7 7 0 0 1 0 14V3z" fill="currentColor" stroke="none"/></svg>`,
  usage: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="12" width="3" height="5" rx="1"/><rect x="8.5" y="8" width="3" height="9" rx="1"/><rect x="14" y="4" width="3" height="13" rx="1"/></svg>`,
  models: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="7" r="3"/><path d="M4 17c0-3.314 2.686-5 6-5s6 1.686 6 5"/><circle cx="15" cy="5" r="1.5"/><circle cx="5" cy="5" r="1.5"/></svg>`,
  skills: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2.5a2 2 0 0 1 2.83 2.83l-9.9 9.9-3.54.71.71-3.54 9.9-9.9z"/></svg>`,
  workspace: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6l7-3 7 3v10l-7 3-7-3V6z"/><path d="M10 3v14M3 6l7 4 7-4"/></svg>`,
  privacy: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="9" width="12" height="9" rx="2"/><path d="M7 9V6a3 3 0 0 1 6 0v3"/><circle cx="10" cy="14" r="1" fill="currentColor" stroke="none"/></svg>`,
  about: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="7"/><path d="M10 9v5"/><circle cx="10" cy="6.5" r="0.75" fill="currentColor" stroke="none"/></svg>`,
};

const menuItems = [
  { id: "general", label: "通用", color: "#636366", svg: svg.general },
  { id: "theme", label: "外观", color: "#5856d6", svg: svg.theme },
  { id: "usage", label: "用量", color: "#34c759", svg: svg.usage },
  { id: "models", label: "模型", color: "#007aff", svg: svg.models },
  { id: "skills", label: "技能", color: "#ff9500", svg: svg.skills },
  { id: "workspace", label: "工作区", color: "#64748b", svg: svg.workspace },
  { id: "privacy", label: "隐私", color: "#ff3b30", svg: svg.privacy },
  { id: "about", label: "关于", color: "#5856d6", svg: svg.about },
];

// --- Theme & accent helpers ---
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

function setAccentColor(hex: string) {
  const doc = document.documentElement;
  doc.style.setProperty("--accent", hex);
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  doc.style.setProperty("--accent-subtle", `rgba(${r}, ${g}, ${b}, 0.10)`);
  const darken = (v: number) => Math.max(0, Math.round(v * 0.8));
  doc.style.setProperty("--accent-hover", `rgb(${darken(r)}, ${darken(g)}, ${darken(b)})`);
}

// --- Persist settings on change ---
watch(() => settings.language, (v) => window.openclaw.settings.set("language", v));
watch(() => settings.autoStart, (v) => window.openclaw.settings.set("autoStart", v));
watch(() => settings.startMinimized, (v) => window.openclaw.settings.set("startMinimized", v));
watch(() => settings.themeMode, (v) => {
  window.openclaw.settings.set("themeMode", v);
  applyTheme(v);
});
watch(() => settings.accentColor, (v) => {
  if (v) {
    window.openclaw.settings.set("accentColor", v);
    setAccentColor(v);
  }
});

// --- Auto-load usage data when tab is selected ---
watch(activeSection, (v) => {
  if (v === "usage" && !usageData.value && !usageLoading.value) {
    loadUsage();
  }
});

onMounted(async () => {
  stateDir.value = await window.openclaw.config.getStateDir();

  // Load persisted app settings
  const saved = await window.openclaw.settings.get();
  if (saved) {
    settings.language = saved.language ?? "zh-CN";
    settings.autoStart = saved.autoStart ?? false;
    settings.startMinimized = saved.startMinimized ?? false;
    settings.themeMode = saved.themeMode ?? "light";
    settings.accentColor = saved.accentColor ?? "#4a90d9";
  }

  // Load existing config for models & gateway
  const config = await window.openclaw.config.read();
  if (config) {
    // Gateway port
    gatewayPort.value = String(config.gateway?.port ?? (gateway.port || 18789));

    // Selected model — strip "provider/" prefix if present
    const primary = config.agents?.defaults?.model?.primary;
    if (primary) {
      selectedModel.value = primary.includes('/') ? primary.split('/').pop()! : primary;
    }

    // Custom models from config
    const providers = config.models?.providers ?? {};
    const loaded: ModelEntry[] = [];
    for (const [key, val] of Object.entries(providers) as [string, any][]) {
      const models = val.models ?? [];
      for (const m of models) {
        loaded.push({
          id: m.id ?? key,
          name: m.name ?? m.id ?? key,
          baseUrl: val.baseUrl ?? "",
          apiKey: val.apiKey ?? "",
          apiFormat: val.api === 'anthropic-messages' ? 'anthropic' : 'openai',
        });
      }
    }
    customModels.value = loaded;
  }

  // Load skills from disk
  try {
    const skills = await window.openclaw.skills.list();
    builtinSkills.value = skills.builtin;
    customSkills.value = skills.custom;
  } catch {
    // Skills listing not available
  }
});

// --- Model & Gateway actions ---

async function persistModelsConfig() {
  // Validate custom models before saving
  for (const m of customModels.value) {
    if (!m.id || !m.id.trim()) {
      throw new Error("模型 ID 不能为空");
    }
    if (m.baseUrl !== undefined && m.baseUrl !== "" && !/^https?:\/\/.+/.test(m.baseUrl)) {
      throw new Error(`模型 "${m.name}" 的 Base URL 格式无效`);
    }
  }

  const config = (await window.openclaw.config.read()) || {};
  const providerConfig: Record<string, any> = {};

  for (const m of customModels.value) {
    const key = m.id.replace(/[^a-zA-Z0-9_-]/g, "_");
    providerConfig[key] = {
      baseUrl: m.baseUrl || "",
      apiKey: m.apiKey || "",
      api: m.apiFormat === 'anthropic' ? 'anthropic-messages' : 'openai-completions',
      models: [{ id: m.id, name: m.name }],
    };
  }

  config.models = { mode: "merge", providers: providerConfig };
  config.agents = config.agents || {};
  config.agents.defaults = config.agents.defaults || {};
  // OpenClaw expects primary in "provider/modelId" format
  const sel = selectedModel.value;
  const selKey = sel.replace(/[^a-zA-Z0-9_-]/g, "_");
  const primary = providerConfig[selKey] ? `${selKey}/${sel}` : sel;
  config.agents.defaults.model = { primary };

  await window.openclaw.config.write(config);
}

async function persistAndRestart(successMsg: string) {
  try {
    await persistModelsConfig();
  } catch (err: any) {
    ElMessage.error("配置保存失败: " + (err.message || err));
    return;
  }
  try {
    await window.openclaw.gateway.restart();
    ElMessage.success(successMsg + "，网关正在重启…");
  } catch (err: any) {
    ElMessage.warning("配置已保存，但网关重启失败: " + (err.message || err));
  }
}

async function selectModel(id: string) {
  selectedModel.value = id;
  await persistAndRestart("模型已切换为 " + id);
}

async function addCustomModel() {
  const name = newModel.name.trim();
  if (!name) { ElMessage.warning("Model name is required"); return; }
  const baseUrl = newModel.baseUrl.trim();
  if (!baseUrl) { ElMessage.warning("Base URL is required"); return; }
  customModels.value.push({
    id: name,
    name,
    baseUrl,
    apiKey: newModel.apiKey.trim(),
    apiFormat: newModel.apiFormat,
  });
  showAddModel.value = false;
  newModel.name = "";
  newModel.baseUrl = "";
  newModel.apiKey = "";
  newModel.apiFormat = "openai";
  testResult.value = null;
  selectedModel.value = name;
  await persistAndRestart("自定义模型已添加");
}

function editCustomModel(idx: number) {
  const m = customModels.value[idx];
  editingIndex.value = idx;
  editModel.name = m.name;
  editModel.baseUrl = m.baseUrl || "";
  editModel.apiKey = m.apiKey || "";
  editModel.apiFormat = m.apiFormat || "openai";
  editTestResult.value = null;
  showEditModel.value = true;
}

async function saveEditModel() {
  const name = editModel.name.trim();
  if (!name) { ElMessage.warning("Model name is required"); return; }
  const baseUrl = editModel.baseUrl.trim();
  if (!baseUrl) { ElMessage.warning("Base URL is required"); return; }
  const idx = editingIndex.value;
  if (idx < 0 || idx >= customModels.value.length) return;
  customModels.value[idx] = {
    id: name,
    name,
    baseUrl,
    apiKey: editModel.apiKey.trim(),
    apiFormat: editModel.apiFormat,
  };
  showEditModel.value = false;
  selectedModel.value = name;
  await persistAndRestart("自定义模型已更新");
}

async function testEditModel() {
  const baseUrl = editModel.baseUrl.trim();
  const apiKey = editModel.apiKey.trim();
  if (!baseUrl) { ElMessage.warning("Base URL is required"); return; }
  editTestLoading.value = true;
  editTestResult.value = null;
  try {
    const result = await window.openclaw.model.testConnection({
      baseUrl,
      apiKey,
      apiFormat: editModel.apiFormat,
      modelName: editModel.name.trim(),
    });
    editTestResult.value = result;
  } catch (err: any) {
    editTestResult.value = { ok: false, message: 'Connection failed: ' + (err.message || 'Network error') };
  } finally {
    editTestLoading.value = false;
  }
}

async function removeCustomModel(idx: number) {
  const removed = customModels.value[idx];
  customModels.value.splice(idx, 1);
  if (removed.id === selectedModel.value && builtinModels.value.length) {
    selectedModel.value = builtinModels.value[0].id;
  }
  await persistAndRestart("自定义模型已删除");
}

async function testCustomModel() {
  const baseUrl = newModel.baseUrl.trim();
  const apiKey = newModel.apiKey.trim();
  if (!baseUrl) { ElMessage.warning("Base URL is required"); return; }
  testLoading.value = true;
  testResult.value = null;
  try {
    const result = await window.openclaw.model.testConnection({
      baseUrl,
      apiKey,
      apiFormat: newModel.apiFormat,
      modelName: newModel.name.trim(),
    });
    testResult.value = result;
  } catch (err: any) {
    testResult.value = { ok: false, message: 'Connection failed: ' + (err.message || 'Network error') };
  } finally {
    testLoading.value = false;
  }
}

async function reconnectGateway() {
  try {
    await window.openclaw.gateway.restart();
    ElMessage.success("Gateway reconnecting...");
  } catch (err: any) {
    ElMessage.error("Reconnect failed: " + err.message);
  }
}

async function resetConnection() {
  try {
    await ElMessageBox.confirm(
      "This will reset the gateway connection. Continue?",
      "Reset Connection",
      { type: "warning" }
    );
    await window.openclaw.gateway.restart();
    ElMessage.success("Connection reset");
  } catch {
    // Cancelled
  }
}

async function saveGatewayPort() {
  const port = parseInt(gatewayPort.value, 10);
  if (!port || port < 1 || port > 65535) {
    ElMessage.warning("Invalid port number");
    return;
  }
  try {
    const config = (await window.openclaw.config.read()) || {};
    config.gateway = config.gateway || {};
    config.gateway.port = port;
    await window.openclaw.config.write(config);
    await window.openclaw.gateway.restart();
    ElMessage.success("Port updated, gateway restarting...");
  } catch (err: any) {
    ElMessage.error("Failed: " + err.message);
  }
}

async function clearChatHistory() {
  try {
    await ElMessageBox.confirm("确定要清除所有聊天记录吗？此操作不可撤销。", "确认", {
      type: "warning",
    });
    chatStore.newSession();
    ElMessage.success("聊天记录已清除");
  } catch {
    // Cancelled
  }
}
</script>

<style scoped>
.settings-view {
  display: flex;
  height: 100%;
  background: var(--bg-primary);
}

/* ── Left sidebar ── */
.settings-sidebar {
  width: 210px;
  min-width: 210px;
  background: var(--bg-primary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 0 12px;
}

.settings-title {
  padding: 0 16px 16px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  display: flex;
  align-items: center;
  gap: 8px;
}

.back-btn {
  background: none;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  cursor: pointer;
  font-size: 16px;
  padding: 4px 10px;
  color: var(--text-primary);
  transition: background 0.15s;
}
.back-btn:hover {
  background: var(--bg-hover, #f0f0f0);
}

.menu-list {
  flex: 1;
  overflow-y: auto;
}

.settings-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px 7px 16px;
  cursor: pointer;
  border-radius: 8px;
  margin: 1px 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 400;
  transition: background 0.1s;
}

.settings-menu-item:hover {
  background: rgba(0, 0, 0, 0.05);
}

.settings-menu-item.active {
  background: var(--accent);
  color: #fff;
}

.menu-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-secondary);
  background: none !important;
}

.settings-menu-item.active .menu-icon {
  color: #fff;
  background: none !important;
}

.menu-icon :deep(svg) {
  width: 16px;
  height: 16px;
}

.menu-label {
  font-size: 13px;
}

/* ── Right content ── */
.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin-bottom: 8px;
  padding-left: 4px;
}

/* Grouped card */
.card-group {
  background: var(--bg-grouped);
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
}

.card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-row);
  gap: 12px;
  min-height: 52px;
}

.card-row.no-border {
  border-bottom: none;
}

.row-label {
  font-size: 13.5px;
  color: var(--text-primary);
  flex-shrink: 0;
}

.row-value {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.placeholder-row {
  justify-content: center;
  padding: 20px 16px;
}

.placeholder-text {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
}

.section-footer {
  font-size: 12px;
  color: var(--text-muted);
  padding: 6px 4px 0;
}

.section-actions {
  margin-top: 16px;
  padding-left: 2px;
}

/* About card */
.about-card {
  background: var(--bg-grouped);
  border-radius: 12px;
  border: 1px solid var(--border);
  padding: 28px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.about-icon {
  font-size: 52px;
  line-height: 1;
  margin-bottom: 4px;
}

.about-name {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.about-version {
  font-size: 13px;
  color: var(--text-secondary);
}

/* Models & API */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
}

.section-header-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.sub-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
  margin-top: 32px;
}

.sub-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 32px;
  margin-bottom: 10px;
}

.badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  padding: 3px 12px;
  border-radius: 20px;
  white-space: nowrap;
}

.badge-green {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
  border: 1px solid rgba(52, 199, 89, 0.25);
}

.badge-red {
  background: rgba(255, 59, 48, 0.12);
  color: #ff3b30;
  border: 1px solid rgba(255, 59, 48, 0.25);
}

.custom-model-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.custom-model-info .row-sub {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-model-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.port-row {
  align-items: flex-start;
  padding: 20px;
  gap: 24px;
  min-height: 80px;
}

.port-info {
  flex: 1;
  min-width: 0;
}

.port-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.port-desc {
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.port-input-group {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px 4px 12px;
}

.port-prefix {
  font-size: 13px;
  color: var(--text-muted);
  white-space: nowrap;
}

.port-input-group :deep(.el-input__wrapper) {
  box-shadow: none !important;
  background: transparent;
  padding: 0;
}

.port-input-group :deep(.el-input__inner) {
  font-size: 13px;
  text-align: center;
  font-weight: 600;
}

.test-result {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--bg-grouped);
  font-size: 13px;
}

.test-ok {
  color: #34c759;
}

.test-fail {
  color: #ff3b30;
}

.skill-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.skill-desc {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge-blue {
  background: rgba(0, 122, 255, 0.12);
  color: #007aff;
  border: 1px solid rgba(0, 122, 255, 0.25);
}

/* Usage section */
.usage-spend {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.budget-bar-wrapper {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  min-width: 180px;
}

.budget-bar {
  width: 100%;
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}

.budget-bar-fill {
  height: 100%;
  background: var(--accent, #4a90d9);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.model-usage-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.model-usage-info .row-sub {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
