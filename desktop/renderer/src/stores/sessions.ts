import { defineStore } from "pinia";
import { ref, computed } from "vue";

export interface Session {
  key: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  preview: string; // last message snippet
}

const STORAGE_KEY = "openclaw-sessions";

function loadFromStorage(): Session[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveToStorage(sessions: Session[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export const useSessionStore = defineStore("sessions", () => {
  const sessions = ref<Session[]>(loadFromStorage());
  const currentKey = ref<string | null>(null);

  const sortedSessions = computed(() =>
    [...sessions.value].sort((a, b) => b.updatedAt - a.updatedAt)
  );

  /** Ensure a session entry exists for the given key. */
  function ensureSession(key: string) {
    if (!sessions.value.find((s) => s.key === key)) {
      sessions.value.push({
        key,
        title: "新对话",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        preview: "",
      });
      saveToStorage(sessions.value);
    }
    currentKey.value = key;
  }

  /** Update session metadata (title / preview). */
  function updateSession(key: string, patch: Partial<Pick<Session, "title" | "preview">>) {
    const s = sessions.value.find((s) => s.key === key);
    if (s) {
      if (patch.title !== undefined) s.title = patch.title;
      if (patch.preview !== undefined) s.preview = patch.preview;
      s.updatedAt = Date.now();
      saveToStorage(sessions.value);
    }
  }

  /** Remove a session. */
  function removeSession(key: string) {
    sessions.value = sessions.value.filter((s) => s.key !== key);
    saveToStorage(sessions.value);
  }

  /** Auto-generate a title from the first user message. */
  function autoTitle(key: string, firstMessage: string) {
    const s = sessions.value.find((s) => s.key === key);
    if (s && s.title === "新对话") {
      s.title = firstMessage.replace(/\n/g, " ").slice(0, 30) || "新对话";
      s.updatedAt = Date.now();
      saveToStorage(sessions.value);
    }
  }

  return {
    sessions,
    currentKey,
    sortedSessions,
    ensureSession,
    updateSession,
    removeSession,
    autoTitle,
  };
});
