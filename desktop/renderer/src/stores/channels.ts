import { defineStore } from "pinia";
import { ref } from "vue";

export interface Channel {
  id: string;
  name: string;
  icon: string;
  type: string;
  connected: boolean;
}

export const useChannelStore = defineStore("channels", () => {
  const channels = ref<Channel[]>([]);

  async function fetchChannels() {
    // TODO: Fetch from gateway via tools API
  }

  return { channels, fetchChannels };
});
