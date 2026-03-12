import { defineStore } from "pinia";
import { ref } from "vue";

export interface ScheduledTask {
  id: string;
  name: string;
  cron: string;
  agentId: string;
  enabled: boolean;
  lastRun?: number;
  lastStatus?: string;
}

export const useTaskStore = defineStore("tasks", () => {
  const tasks = ref<ScheduledTask[]>([]);

  async function fetchTasks() {
    // TODO: Fetch from gateway via tools API
  }

  return { tasks, fetchTasks };
});
