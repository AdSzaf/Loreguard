<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api, ApiError } from "../services/api";
import type { DashboardSummary, SyncResult } from "../types/api";
import SeverityBadge from "../components/SeverityBadge.vue";

const dashboard = ref<DashboardSummary | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const syncing = ref(false);
const lastSync = ref<SyncResult | null>(null);
const syncError = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;

  try {
    dashboard.value = await api.dashboard();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się połączyć z API.";
  } finally {
    loading.value = false;
  }
}

async function runSync() {
  syncing.value = true;
  syncError.value = null;

  try {
    lastSync.value = await api.syncVault();
    await load();
  } catch (e) {
    syncError.value = e instanceof ApiError ? e.message : "Synchronizacja nie powiodła się.";
  } finally {
    syncing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <header class="page__header">
      <div>
        <h1 class="page__title">Dashboard</h1>
        <p class="page__subtitle">Stan spójności Twojego świata</p>
      </div>

      <button class="btn btn--primary" :disabled="syncing" @click="runSync">
        {{ syncing ? "Synchronizuję…" : "Synchronizuj vault" }}
      </button>
    </header>

    <p v-if="syncError" class="banner banner--error">{{ syncError }}</p>
    <p v-else-if="lastSync" class="banner banner--ok">
      Zsynchronizowano {{ lastSync.documents_synced }} dokumentów. Nowe konflikty:
      {{ lastSync.conflicts.created }} (pominięto już śledzone:
      {{ lastSync.conflicts.skipped_existing }}).
    </p>

    <p v-if="error" class="banner banner--error">{{ error }}</p>

    <template v-if="loading">
      <p class="muted">Ładowanie…</p>
    </template>

    <template v-else-if="dashboard">
      <section class="stats">
        <div class="stat-card">
          <span class="stat-card__value mono">{{ dashboard.documents }}</span>
          <span class="stat-card__label">Dokumenty</span>
        </div>
        <div class="stat-card">
          <span class="stat-card__value mono">{{ dashboard.entities }}</span>
          <span class="stat-card__label">Encje</span>
        </div>
        <div class="stat-card">
          <span class="stat-card__value mono">{{ dashboard.facts }}</span>
          <span class="stat-card__label">Fakty</span>
        </div>
        <div class="stat-card">
          <span class="stat-card__value mono">{{ dashboard.events }}</span>
          <span class="stat-card__label">Wydarzenia</span>
        </div>
        <div class="stat-card stat-card--conflicts">
          <span class="stat-card__value mono">{{ dashboard.conflicts_open }}</span>
          <span class="stat-card__label">Otwarte konflikty</span>
        </div>
      </section>

      <section class="health">
        <div class="health__label">
          <span>Canon Health</span>
          <span class="mono">{{ dashboard.canon_health_percent }}%</span>
        </div>
        <div class="health__bar">
          <div
            class="health__bar-fill"
            :style="{ width: `${dashboard.canon_health_percent}%` }"
          />
        </div>
      </section>

      <section class="panel">
        <div class="panel__header">
          <h2 class="panel__title">Otwarte konflikty</h2>
          <RouterLink to="/conflicts" class="link">zobacz wszystkie →</RouterLink>
        </div>

        <p v-if="dashboard.open_conflicts_preview.length === 0" class="muted">
          Brak otwartych konfliktów. Kanon jest spójny.
        </p>

        <ul v-else class="conflict-preview-list">
          <li
            v-for="conflict in dashboard.open_conflicts_preview"
            :key="conflict.id"
            class="conflict-preview-item"
          >
            <SeverityBadge :severity="conflict.severity" />
            <div class="conflict-preview-item__body">
              <span class="conflict-preview-item__entity">{{ conflict.entity }}</span>
              <span class="conflict-preview-item__explanation">{{ conflict.explanation }}</span>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 960px;
}

.page__header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 24px;
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

.btn {
  font-size: 13px;
  font-weight: 600;
  padding: 9px 16px;
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

.btn--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #14161d;
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

.banner--ok {
  background: var(--severity-low-soft);
  color: var(--severity-low);
}

.muted {
  color: var(--text-muted);
  font-size: 14px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-card--conflicts {
  border-color: var(--severity-high);
}

.stat-card__value {
  font-size: 24px;
  font-weight: 600;
}

.stat-card__label {
  font-size: 12px;
  color: var(--text-muted);
}

.health {
  margin-bottom: 24px;
}

.health__label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 6px;
  color: var(--text-muted);
}

.health__bar {
  height: 8px;
  border-radius: 999px;
  background: var(--surface-raised);
  overflow: hidden;
}

.health__bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--severity-low), var(--accent));
  transition: width 0.3s ease;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
}

.panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel__title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}

.link {
  font-size: 13px;
  color: var(--accent-strong);
  text-decoration: none;
}

.conflict-preview-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.conflict-preview-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px;
  border-radius: var(--radius);
  background: var(--surface-raised);
}

.conflict-preview-item__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.conflict-preview-item__entity {
  font-size: 13px;
  font-weight: 600;
}

.conflict-preview-item__explanation {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
