<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, ApiError } from "../services/api";
import type { EventView } from "../types/api";

const events = ref<EventView[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

const sorted = computed(() =>
  [...events.value].sort((a, b) => {
    if (a.date_start_year === null) return 1;
    if (b.date_start_year === null) return -1;
    return a.date_start_year - b.date_start_year;
  }),
);

async function load() {
  loading.value = true;
  error.value = null;

  try {
    events.value = await api.events();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się pobrać wydarzeń.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <header class="page__header">
      <h1 class="page__title">Oś czasu</h1>
    </header>

    <p v-if="error" class="banner banner--error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Ładowanie…</p>
    <p v-else-if="sorted.length === 0" class="muted">
      Brak wydarzeń. Dodaj tag/pole daty do notatek, żeby pojawiły się tutaj.
    </p>

    <ol v-else class="timeline">
      <li v-for="event in sorted" :key="event.id" class="timeline-item">
        <div class="timeline-item__year mono">
          {{ event.date_text ?? "?" }}
        </div>
        <div class="timeline-item__body">
          <span class="timeline-item__name">{{ event.name }}</span>
          <span v-if="event.location" class="timeline-item__meta">📍 {{ event.location }}</span>
          <span v-if="event.outcome" class="timeline-item__meta">{{ event.outcome }}</span>
          <div v-if="event.participants.length" class="timeline-item__participants">
            <span
              v-for="p in event.participants"
              :key="p.name"
              class="participant-chip"
            >
              {{ p.name }}<template v-if="p.role"> ({{ p.role }})</template>
            </span>
          </div>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
}

.page__title {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 16px;
}

.banner--error {
  background: var(--severity-high-soft);
  color: var(--severity-high);
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
}

.muted {
  color: var(--text-muted);
  font-size: 14px;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  border-left: 2px solid var(--border);
  margin-left: 8px;
}

.timeline-item {
  position: relative;
  padding: 0 0 20px 24px;
}

.timeline-item::before {
  content: "";
  position: absolute;
  left: -6px;
  top: 4px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
}

.timeline-item__year {
  font-size: 12px;
  color: var(--accent-strong);
  margin-bottom: 4px;
}

.timeline-item__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.timeline-item__name {
  font-weight: 600;
  font-size: 15px;
}

.timeline-item__meta {
  font-size: 12px;
  color: var(--text-muted);
}

.timeline-item__participants {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.participant-chip {
  font-size: 11px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--text-muted);
}
</style>
