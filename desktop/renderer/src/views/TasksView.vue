<template>
  <div class="tasks-view">
    <div class="view-header">
      <h2>定时任务</h2>
      <p class="view-desc">查看和管理 OpenClaw 中已配置的定时任务</p>
    </div>

    <div v-if="taskStore.tasks.length === 0" class="empty-state">
      <div class="empty-title">暂无定时任务</div>
      <div class="empty-desc">
        在 OpenClaw 配置中添加定时任务后，这里会自动显示。
      </div>
    </div>

    <el-table
      v-else
      :data="taskStore.tasks"
      style="width: 100%"
      :header-cell-style="{ background: 'var(--bg-secondary)' }"
    >
      <el-table-column prop="name" label="任务名称" />
      <el-table-column prop="cron" label="Cron 表达式" width="180" />
      <el-table-column prop="agentId" label="目标智能体" width="150" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? "启用" : "禁用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上次运行" width="160">
        <template #default="{ row }">
          <span v-if="row.lastRun">{{ new Date(row.lastRun).toLocaleString("zh-CN") }}</span>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { useTaskStore } from "@/stores/tasks";

const taskStore = useTaskStore();
</script>

<style scoped>
.tasks-view {
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

.text-muted {
  color: var(--text-muted);
}
</style>
