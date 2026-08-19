<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { api, ApiError } from "../services/api";
import type { EntityDetail } from "../types/api";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ id: string }>();

const entity = ref<EntityDetail | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;

  try {
    entity.value = await api.entity(Number(props.id));
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się pobrać encji.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.id, load);
</script>

<template>
  <div class="page">
    <p v-if="error" class="banner banner--error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Ładowanie…</p>

    <template v-else-if="entity">
      <header class="page__header">
        <h1 class="page__title">{{ entity.name }}</h1>
        <p v-if="entity.aliases.length" class="page__aliases">
          znany też jako: {{ entity.aliases.join(", ") }}
        </p>
      </header>

      <section class="panel">
        <h2 class="panel__title">Fakty</h2>
        <p v-if="entity.facts.length === 0" class="muted">Brak zapisanych faktów.</p>
        <table v-else class="facts-table">
          <tbody>
            <tr v-for="fact in entity.facts" :key="fact.id">
              <td class="facts-table__predicate mono">{{ fact.predicate }}</td>
              <td>{{ fact.value }}</td>
              <td class="facts-table__source mono">{{ fact.source_document }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="panel">
        <h2 class="panel__title">Konflikty dotyczące tej encji</h2>
        <p v-if="entity.conflicts.length === 0" class="muted">Brak konfliktów.</p>
        <ul v-else class="conflict-list">
          <li v-for="conflict in entity.conflicts" :key="conflict.id" class="conflict-item">
            <StatusBadge :status="conflict.status" />
            <span>{{ conflict.explanation }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
}

.page__header {
  margin-bottom: 20px;
}

.page__title {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 4px;
}

.page__aliases {
  color: var(--text-muted);
  font-size: 13px;
  margin: 0;
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

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px;
  margin-bottom: 16px;
}

.panel__title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
}

.facts-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.facts-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-soft);
}

.facts-table__predicate {
  color: var(--accent-strong);
  white-space: nowrap;
}

.facts-table__source {
  color: var(--text-faint);
  text-align: right;
  font-size: 11px;
}

.conflict-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.conflict-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
}
</style>
