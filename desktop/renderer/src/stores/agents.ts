import { defineStore } from "pinia";
import { ref } from "vue";

export interface Agent {
  id: string;
  name: string;
  description?: string;
}

export const useAgentStore = defineStore("agents", () => {
  const agents = ref<Agent[]>([
    { id: "main", name: "默认智能体", description: "默认对话智能体" },
  ]);
  const currentAgentId = ref("main");

  async function fetchAgents() {
    // TODO: Fetch agent list from gateway via tools API
    // For now, use the default "main" agent
  }

  return { agents, currentAgentId, fetchAgents };
});
