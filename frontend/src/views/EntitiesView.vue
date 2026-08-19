<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api, ApiError } from "../services/api";
import type { EntitySummary, EntityType } from "../types/api";

const entities = ref<EntitySummary[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const typeFilter = ref<EntityType | "all">("all");

const TYPE_LABELS: Record<EntityType, string> = {
  person: "Postać",
  deity: "Bóstwo",
  country: "Kraj",
  region: "Region",
  place: "Miejsce",
  race: "Rasa",
  organization: "Organizacja",
  faction: "Frakcja",
  item: "Przedmiot",
  event: "Wydarzenie",
  concept: "Koncepcja",
  other: "Inne",
};

async function load() {
  loading.value = true;
  error.value = null;

  try {
    entities.value = await api.entities(
      typeFilter.value === "all" ? undefined : typeFilter.value,
    );
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się pobrać encji.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <header class="page__header">
      <h1 class="page__title">Encje</h1>
    </header>

    <select v-model="typeFilter" class="select" @change="load">
      <option value="all">Wszystkie typy</option>
      <option v-for="(label, value) in TYPE_LABELS" :key="value" :value="value">
        {{ label }}
      </option>
    </select>

    <p v-if="error" class="banner banner--error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Ładowanie…</p>
    <p v-else-if="entities.length === 0" class="muted">Brak encji.</p>

    <ul v-else class="entity-list">
      <li v-for="entity in entities" :key="entity.id">
        <RouterLink :to="`/entities/${entity.id}`" class="entity-card">
          <span class="entity-card__name">{{ entity.name }}</span>
          <span class="entity-card__type mono">{{ TYPE_LABELS[entity.entity_type] }}</span>
        </RouterLink>
      </li>
    </ul>
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

.select {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: var(--radius);
  padding: 8px 10px;
  font-size: 13px;
  margin-bottom: 16px;
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

.entity-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.entity-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  text-decoration: none;
  color: var(--text);
}

.entity-card:hover {
  border-color: var(--accent);
}

.entity-card__name {
  font-weight: 600;
  font-size: 14px;
}

.entity-card__type {
  font-size: 11px;
  color: var(--text-faint);
}
</style>
