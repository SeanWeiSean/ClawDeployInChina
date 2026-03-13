import { defineStore } from "pinia";
import { ref } from "vue";

export const useGatewayStore = defineStore("gateway", () => {
  const status = ref("stopped");
  const port = ref(0);
  const logs = ref<string[]>([]);

  function addLog(msg: string) {
    logs.value.push(msg);
    // Keep last 500 lines
    if (logs.value.length > 500) {
      logs.value = logs.value.slice(-500);
    }
  }

  return { status, port, logs, addLog };
});
