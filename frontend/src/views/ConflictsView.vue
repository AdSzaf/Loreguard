<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ApiError } from "../services/api";
import type { ConflictStatus, ConflictView } from "../types/api";
import SeverityBadge from "../components/SeverityBadge.vue";
import StatusBadge from "../components/StatusBadge.vue";

const conflicts = ref<ConflictView[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const statusFilter = ref<ConflictStatus | "all">("open");

const noteDrafts = ref<Record<number, string>>({});
const resolvingId = ref<number | null>(null);

const STATUS_OPTIONS: { value: ConflictStatus | "all"; label: string }[] = [
  { value: "open", label: "Otwarte" },
  { value: "confirmed", label: "Potwierdzone" },
  { value: "dismissed", label: "Odrzucone" },
  { value: "explained", label: "Wyjaśnione" },
  { value: "all", label: "Wszystkie" },
];

async function load() {
  loading.value = true;
  error.value = null;

  try {
    conflicts.value = await api.conflicts(
      statusFilter.value === "all" ? undefined : statusFilter.value,
    );
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się pobrać konfliktów.";
  } finally {
    loading.value = false;
  }
}

async function resolve(conflict: ConflictView, status: ConflictStatus) {
  resolvingId.value = conflict.id;

  try {
    await api.resolveConflict(conflict.id, status, noteDrafts.value[conflict.id]);
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się zapisać decyzji.";
  } finally {
    resolvingId.value = null;
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <header class="page__header">
      <div>
        <h1 class="page__title">Konflikty</h1>
        <p class="page__subtitle">
          LoreGuard nigdy nie edytuje Twoich notatek — Ty jesteś ostatecznym arbitrem.
        </p>
      </div>
    </header>

    <div class="filters">
      <button
        v-for="option in STATUS_OPTIONS"
        :key="option.value"
        class="filter"
        :class="{ 'filter--active': statusFilter === option.value }"
        @click="statusFilter = option.value; load()"
      >
        {{ option.label }}
      </button>
    </div>

    <p v-if="error" class="banner banner--error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Ładowanie…</p>
    <p v-else-if="conflicts.length === 0" class="muted">
      Brak konfliktów w tym widoku.
    </p>

    <ul v-else class="conflict-list">
      <li v-for="conflict in conflicts" :key="conflict.id" class="conflict-card">
        <div class="conflict-card__header">
          <div class="conflict-card__badges">
            <SeverityBadge :severity="conflict.severity" />
            <StatusBadge :status="conflict.status" />
            <span class="conflict-card__rule mono">{{ conflict.rule_name }}</span>
          </div>
          <span class="conflict-card__entity">{{ conflict.entity }}</span>
        </div>

        <p class="conflict-card__explanation">{{ conflict.explanation }}</p>

        <div v-if="conflict.fact_a && conflict.fact_b" class="evidence">
          <div class="evidence__side">
            <span class="evidence__source mono">{{ conflict.fact_a.source_document }}</span>
            <span class="evidence__line">
              <strong>{{ conflict.fact_a.predicate }}</strong>: {{ conflict.fact_a.value }}
            </span>
          </div>
          <div class="evidence__vs">vs</div>
          <div class="evidence__side">
            <span class="evidence__source mono">{{ conflict.fact_b.source_document }}</span>
            <span class="evidence__line">
              <strong>{{ conflict.fact_b.predicate }}</strong>: {{ conflict.fact_b.value }}
            </span>
          </div>
        </div>

        <div v-else-if="conflict.related_event" class="evidence evidence--single">
          <span class="evidence__line">Wydarzenie: <strong>{{ conflict.related_event }}</strong></span>
        </div>

        <p v-if="conflict.resolution_note" class="resolution-note">
          <span class="mono">notatka:</span> {{ conflict.resolution_note }}
        </p>

        <div v-if="conflict.status === 'open'" class="actions">
          <input
            v-model="noteDrafts[conflict.id]"
            class="actions__note"
            type="text"
            placeholder="Notatka wyjaśniająca (opcjonalnie)…"
          />
          <div class="actions__buttons">
            <button
              class="btn btn--confirm"
              :disabled="resolvingId === conflict.id"
              @click="resolve(conflict, 'confirmed')"
            >
              Potwierdź konflikt
            </button>
            <button
              class="btn"
              :disabled="resolvingId === conflict.id"
              @click="resolve(conflict, 'dismissed')"
            >
              To nie jest konflikt
            </button>
            <button
              class="btn"
              :disabled="resolvingId === conflict.id"
              @click="resolve(conflict, 'explained')"
            >
              Dodaj wyjaśnienie
            </button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.page {
  max-width: 860px;
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

.page__subtitle {
  color: var(--text-muted);
  margin: 0;
  font-size: 14px;
}

.filters {
  display: flex;
  gap: 6px;
  margin-bottom: 20px;
}

.filter {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.filter--active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent-strong);
}

.banner {
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
  margin-bottom: 16px;
}

.banner--error {
  background: var(--severity-high-soft);
  color: var(--severity-high);
}

.muted {
  color: var(--text-muted);
  font-size: 14px;
}

.conflict-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.conflict-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px;
}

.conflict-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}

.conflict-card__badges {
  display: flex;
  align-items: center;
  gap: 8px;
}

.conflict-card__rule {
  font-size: 11px;
  color: var(--text-faint);
}

.conflict-card__entity {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
}

.conflict-card__explanation {
  font-size: 14px;
  color: var(--text);
  margin: 0 0 12px;
  line-height: 1.5;
}

.evidence {
  display: flex;
  align-items: stretch;
  gap: 12px;
  background: var(--surface-raised);
  border-radius: var(--radius);
  padding: 12px;
  margin-bottom: 12px;
}

.evidence--single {
  display: block;
}

.evidence__side {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.evidence__source {
  font-size: 11px;
  color: var(--text-faint);
}

.evidence__line {
  font-size: 13px;
}

.evidence__vs {
  align-self: center;
  font-size: 11px;
  color: var(--text-faint);
  text-transform: uppercase;
}

.resolution-note {
  font-size: 13px;
  color: var(--text-muted);
  background: var(--surface-raised);
  border-radius: var(--radius);
  padding: 8px 12px;
  margin-bottom: 12px;
}

.actions {
  border-top: 1px solid var(--border-soft);
  padding-top: 12px;
}

.actions__note {
  width: 100%;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 10px;
  color: var(--text);
  font-size: 13px;
  margin-bottom: 10px;
}

.actions__buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.btn {
  font-size: 13px;
  font-weight: 600;
  padding: 8px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--text);
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.btn--confirm {
  background: var(--severity-high-soft);
  border-color: var(--severity-high);
  color: var(--severity-high);
}
</style>
