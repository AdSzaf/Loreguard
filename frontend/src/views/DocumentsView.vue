<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { api, ApiError } from "../services/api";
import type { DocumentSummary, LlmExtractionResult, LlmStatus } from "../types/api";

const documents = ref<DocumentSummary[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

const llmStatus = ref<LlmStatus | null>(null);

const extracting = reactive<Record<number, boolean>>({});
const results = reactive<Record<number, LlmExtractionResult>>({});

async function load() {
  loading.value = true;
  error.value = null;

  try {
    [documents.value, llmStatus.value] = await Promise.all([
      api.documents(),
      api.llmStatus(),
    ]);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się pobrać dokumentów.";
  } finally {
    loading.value = false;
  }
}

async function extract(doc: DocumentSummary) {
  extracting[doc.id] = true;
  delete results[doc.id];

  try {
    results[doc.id] = await api.extractLlmFacts(doc.id);
  } catch (e) {
    results[doc.id] = {
      error: e instanceof ApiError ? e.message : "Ekstrakcja nie powiodła się.",
    };
  } finally {
    extracting[doc.id] = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <header class="page__header">
      <div>
        <h1 class="page__title">Dokumenty</h1>
        <p class="page__subtitle">
          Ekstrakcja faktów z prozy przez LLM — osobno dla każdego dokumentu.
        </p>
      </div>

      <div v-if="llmStatus" class="llm-status" :class="{ 'llm-status--off': !llmStatus.active_provider }">
        <span class="llm-status__dot" />
        <span v-if="llmStatus.active_provider">
          {{ llmStatus.active_provider }} · <span class="mono">{{ llmStatus.model }}</span>
        </span>
        <span v-else>Brak skonfigurowanego LLM</span>
      </div>
    </header>

    <p v-if="error" class="banner banner--error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Ładowanie…</p>
    <p v-else-if="documents.length === 0" class="muted">Brak dokumentów. Zsynchronizuj vault na Dashboardzie.</p>

    <ul v-else class="document-list">
      <li v-for="doc in documents" :key="doc.id" class="document-card">
        <div class="document-card__row">
          <div class="document-card__info">
            <span class="document-card__title">{{ doc.title }}</span>
            <span class="document-card__path mono">{{ doc.path }}</span>
          </div>

          <button
            class="btn"
            :disabled="extracting[doc.id] || !llmStatus?.active_provider"
            :title="!llmStatus?.active_provider ? 'Skonfiguruj ANTHROPIC_API_KEY lub GEMINI_API_KEY w .env' : ''"
            @click="extract(doc)"
          >
            {{ extracting[doc.id] ? "Analizuję…" : "Wyciągnij fakty (LLM)" }}
          </button>
        </div>

        <div v-if="results[doc.id]" class="result">
          <p v-if="results[doc.id].error" class="banner banner--error">
            {{ results[doc.id].error }}
          </p>

          <template v-else>
            <p class="result__summary">
              Znaleziono {{ results[doc.id].facts_extracted ?? 0 }} fakt(ów).
              <template v-if="results[doc.id].conflicts">
                Nowe konflikty: {{ results[doc.id].conflicts!.created }}
                (pominięto już śledzone: {{ results[doc.id].conflicts!.skipped_existing }}).
              </template>
            </p>

            <ul v-if="results[doc.id].facts?.length" class="fact-list">
              <li v-for="(fact, i) in results[doc.id].facts" :key="i" class="fact-item">
                <div class="fact-item__row">
                  <span class="fact-item__predicate mono">{{ fact.predicate }}</span>
                  <span class="fact-item__value">{{ fact.value }}</span>
                  <span class="fact-item__confidence mono">{{ Math.round(fact.confidence * 100) }}%</span>
                </div>
                <p v-if="fact.source_text" class="fact-item__quote">„{{ fact.source_text }}"</p>
              </li>
            </ul>
          </template>
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
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
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
  font-size: 13px;
}

.llm-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 12px;
  white-space: nowrap;
}

.llm-status__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--severity-low);
}

.llm-status--off .llm-status__dot {
  background: var(--severity-high);
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

.document-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.document-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
}

.document-card__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.document-card__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.document-card__title {
  font-weight: 600;
  font-size: 14px;
}

.document-card__path {
  font-size: 11px;
  color: var(--text-faint);
}

.btn {
  font-size: 12px;
  font-weight: 600;
  padding: 7px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--text);
  cursor: pointer;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.result {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-soft);
}

.result__summary {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0 0 10px;
}

.fact-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fact-item {
  background: var(--surface-raised);
  border-radius: var(--radius);
  padding: 8px 10px;
}

.fact-item__row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.fact-item__predicate {
  color: var(--accent-strong);
}

.fact-item__value {
  flex: 1;
}

.fact-item__confidence {
  font-size: 11px;
  color: var(--text-faint);
}

.fact-item__quote {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-faint);
  font-style: italic;
}
</style>
