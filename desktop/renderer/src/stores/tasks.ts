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
  const loading = ref(false);

  async function fetchTasks() {
    loading.value = true;
    try {
      const res = await window.openclaw.cron.list();
      const jobs = Array.isArray(res.jobs) ? res.jobs : [];
      tasks.value = jobs.map((j: any) => {
        let cronExpr = "";
        if (j.schedule?.kind === "cron") cronExpr = j.schedule.expr || "";
        else if (j.schedule?.kind === "at") cronExpr = j.schedule.at || "";
        else if (j.schedule?.kind === "every") cronExpr = `every ${j.schedule.everyMs}ms`;

        return {
          id: j.jobId || j.id || "",
          name: j.name || j.jobId || "unnamed",
          cron: cronExpr,
          agentId: j.agentId || "",
          enabled: j.enabled ?? true,
          lastRun: j.lastRun,
          lastStatus: j.lastStatus,
        } as ScheduledTask;
      });
    } catch (err) {
      console.error("[tasks] fetchTasks failed:", err);
    } finally {
      loading.value = false;
    }
  }

  return { tasks, loading, fetchTasks };
});
