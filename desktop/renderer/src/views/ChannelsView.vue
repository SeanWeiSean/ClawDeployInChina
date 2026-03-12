<template>
  <div class="channels-view">
    <div class="view-header">
      <h2>消息频道</h2>
      <p class="view-desc">管理已对接的外部即时通讯频道</p>
    </div>

    <div v-if="channelStore.channels.length === 0" class="empty-state">
      <div class="empty-title">暂无消息频道</div>
      <div class="empty-desc">
        在 OpenClaw 配置中添加 IM channel 后，这里会自动显示。
      </div>
    </div>

    <div v-else class="channel-grid">
      <div
        v-for="ch in channelStore.channels"
        :key="ch.id"
        class="channel-card"
      >
        <div class="channel-icon">{{ ch.icon }}</div>
        <div class="channel-info">
          <div class="channel-name">{{ ch.name }}</div>
          <div class="channel-type">{{ ch.type }}</div>
        </div>
        <div class="channel-status" :class="ch.connected ? 'online' : 'offline'">
          {{ ch.connected ? "已连接" : "未连接" }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useChannelStore } from "@/stores/channels";

const channelStore = useChannelStore();
</script>

<style scoped>
.channels-view {
  height: 100%;
  overflow-y: auto;
  padding: 24px 32px;
}

.view-header {
  margin-bottom: 24px;
}

.view-header h2 {
  font-size: 20px;
  font-weight: 600;
}

.view-desc {
  color: var(--text-secondary);
  font-size: 13px;
  margin-top: 4px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-secondary);
}

.empty-desc {
  font-size: 13px;
  margin-top: 8px;
  text-align: center;
  max-width: 300px;
}

.channel-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.channel-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border-color 0.15s;
}

.channel-card:hover {
  border-color: var(--border-light);
}

.channel-icon {
  font-size: 28px;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.channel-info {
  flex: 1;
}

.channel-name {
  font-weight: 500;
}

.channel-type {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.channel-status {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
}

.channel-status.online {
  background: rgba(52, 199, 89, 0.12);
  color: #1a8a3e;
}

.channel-status.offline {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-muted);
}
</style>
