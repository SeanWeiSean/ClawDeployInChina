<template>
  <div class="wizard-view">
    <div class="wizard-card">
      <el-steps :active="step" align-center finish-status="success" class="wizard-steps">
        <el-step title="欢迎" />
        <el-step title="网络" />
        <el-step title="AI 配置" />
        <el-step title="完成" />
      </el-steps>

      <!-- Step 0: Welcome -->
      <div v-if="step === 0" class="step-content">
        <h2>欢迎使用 OpenClaw</h2>
        <p class="step-desc">让我们快速完成初始配置</p>
        <el-button type="primary" size="large" @click="step = 1">
          开始配置
        </el-button>
      </div>

      <!-- Step 1: Network -->
      <div v-if="step === 1" class="step-content">
        <h2>网络配置</h2>
        <p class="step-desc">选择 NPM 镜像源以加速包下载</p>
        <el-form label-position="top" style="max-width: 400px; margin: 0 auto">
          <el-form-item label="NPM 镜像">
            <el-select v-model="form.mirror" style="width: 100%">
              <el-option label="默认 (npmjs.org)" value="default" />
              <el-option label="淘宝镜像 (npmmirror.com)" value="npmmirror" />
              <el-option label="腾讯云镜像" value="tencent" />
            </el-select>
          </el-form-item>
        </el-form>
        <div class="step-actions">
          <el-button @click="step = 0">上一步</el-button>
          <el-button type="primary" @click="step = 2">下一步</el-button>
        </div>
      </div>

      <!-- Step 2: AI Provider -->
      <div v-if="step === 2" class="step-content">
        <h2>AI 配置</h2>
        <p class="step-desc">配置你的 AI 提供商</p>
        <el-form label-position="top" style="max-width: 400px; margin: 0 auto">
          <el-form-item label="AI 提供商">
            <el-select v-model="form.provider" style="width: 100%">
              <el-option label="Anthropic (Claude)" value="anthropic" />
              <el-option label="OpenAI" value="openai" />
              <el-option label="自定义 (OpenAI 兼容)" value="custom" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="form.apiKey"
              type="password"
              show-password
              placeholder="sk-..."
            />
          </el-form-item>
          <el-form-item v-if="form.provider === 'custom'" label="Base URL">
            <el-input v-model="form.baseUrl" placeholder="https://api.example.com/v1" />
          </el-form-item>
          <el-form-item v-if="form.provider === 'custom'" label="模型名称">
            <el-input v-model="form.modelName" placeholder="model-id" />
          </el-form-item>
          <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
        </el-form>
        <div class="step-actions">
          <el-button @click="step = 1">上一步</el-button>
          <el-button @click="skipSetup" text>稍后配置</el-button>
          <el-button type="primary" @click="saveAndFinish" :loading="saving">
            完成配置
          </el-button>
        </div>
      </div>

      <!-- Step 3: Done -->
      <div v-if="step === 3" class="step-content">
        <h2>配置完成</h2>
        <p class="step-desc">{{ statusText }}</p>
        <div class="spinner" v-if="launching"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();

const step = ref(0);
const saving = ref(false);
const launching = ref(false);
const statusText = ref("正在启动 Gateway...");
const errorMsg = ref("");

const form = reactive({
  mirror: "default",
  provider: "anthropic",
  apiKey: "",
  baseUrl: "",
  modelName: "",
});

async function saveAndFinish() {
  errorMsg.value = "";

  if (!form.apiKey.trim()) {
    errorMsg.value = "请输入 API Key";
    return;
  }
  if (form.provider === "custom" && !form.baseUrl.trim()) {
    errorMsg.value = "请输入 Base URL";
    return;
  }

  saving.value = true;
  try {
    const crypto = { randomUUID: () => Math.random().toString(36).slice(2) + Date.now().toString(36) };
    const token = crypto.randomUUID();

    const providerConfig: Record<string, any> = {};
    let primaryModel: string;

    if (form.provider === "anthropic") {
      providerConfig.anthropic = { apiKey: form.apiKey };
      primaryModel = "anthropic/claude-sonnet-4-20250514";
    } else if (form.provider === "openai") {
      providerConfig.openai = { apiKey: form.apiKey };
      primaryModel = "openai/gpt-4o";
    } else {
      providerConfig.custom = {
        baseUrl: form.baseUrl,
        apiKey: form.apiKey,
        api: "openai-completions",
        models: [{ id: form.modelName || "default", name: form.modelName || "default" }],
      };
      primaryModel = `custom/${form.modelName || "default"}`;
    }

    const config = {
      agents: {
        defaults: {
          model: { primary: primaryModel },
        },
      },
      models: { mode: "merge", providers: providerConfig },
      gateway: {
        port: 18789,
        bind: "loopback",
        mode: "local",
        auth: { mode: "token", token },
      },
    };

    await window.openclaw.config.write(config);
    step.value = 3;
    launching.value = true;

    // Wait for gateway to start, then navigate to main UI
    statusText.value = "配置已保存，正在启动...";
    await new Promise((r) => setTimeout(r, 2000));
    launching.value = false;
    statusText.value = "启动完成！";
    await new Promise((r) => setTimeout(r, 500));
    router.push("/chat");
  } catch (err: any) {
    errorMsg.value = "保存失败: " + (err.message || String(err));
  } finally {
    saving.value = false;
  }
}

async function skipSetup() {
  const config = {
    gateway: {
      port: 18789,
      bind: "loopback",
      mode: "local",
    },
  };
  await window.openclaw.config.write(config);
  router.push("/chat");
}
</script>

<style scoped>
.wizard-view {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
}

.wizard-card {
  width: 560px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 32px;
}

.wizard-steps {
  margin-bottom: 32px;
}

.step-content {
  text-align: center;
}

.step-content h2 {
  font-size: 22px;
  margin-bottom: 8px;
}

.step-desc {
  color: var(--text-secondary);
  margin-bottom: 24px;
  font-size: 14px;
}

.welcome-logo,
.done-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 24px;
}

.error-msg {
  color: var(--danger);
  font-size: 13px;
  margin-top: 8px;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 16px auto;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
