import { createRouter, createWebHashHistory } from "vue-router";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/",
      redirect: "/chat",
    },
    {
      path: "/chat/:agentId?",
      name: "chat",
      component: () => import("@/views/ChatView.vue"),
    },
    {
      path: "/channels",
      name: "channels",
      component: () => import("@/views/ChannelsView.vue"),
    },
    {
      path: "/tasks",
      name: "tasks",
      component: () => import("@/views/TasksView.vue"),
    },
    {
      path: "/settings/:section?",
      name: "settings",
      component: () => import("@/views/SettingsView.vue"),
    },
    {
      path: "/setup",
      name: "setup",
      component: () => import("@/views/SetupWizard.vue"),
    },
  ],
});

export default router;
