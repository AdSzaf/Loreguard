<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { RouterLink } from "vue-router";
import { api, ApiError } from "../services/api";
import type {
  BulkLlmExtractionResult,
  DocumentSummary,
  LlmExtractionResult,
  LlmStatus,
} from "../types/api";
import Pagination from "../components/Pagination.vue";

const PAGE_SIZE = 25;

const documents = ref<DocumentSummary[]>([]);
const page = ref(1);
const totalPages = ref(0);
const total = ref(0);
const loading = ref(true);
const error = ref<string | null>(null);

const llmStatus = ref<LlmStatus | null>(null);

const extracting = reactive<Record<number, boolean>>({});
const results = reactive<Record<number, LlmExtractionResult>>({});

const bulkRunning = ref(false);
const bulkResult = ref<BulkLlmExtractionResult | null>(null);

async function load() {
  loading.value = true;
  error.value = null;

  try {
    const [docsPage, status] = await Promise.all([
      api.documents(page.value, PAGE_SIZE),
      api.llmStatus(),
    ]);
    documents.value = docsPage.items;
    totalPages.value = docsPage.total_pages;
    total.value = docsPage.total;
    llmStatus.value = status;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się pobrać dokumentów.";
  } finally {
    loading.value = false;
  }
}

function changePage(newPage: number) {
  page.value = newPage;
  load();
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
    await load();
  }
}

async function runBulk(force: boolean) {
  bulkRunning.value = true;
  bulkResult.value = null;

  try {
    // Bulk processing always covers every document in the vault,
    // regardless of which page is currently shown -- pagination is
    // purely a listing concern (see the /api/vault/extract-llm-facts
    // docstring on the backend).
    bulkResult.value = await api.extractLlmFactsBulk(force);
  } catch (e) {
    bulkResult.value = {
      error: e instanceof ApiError ? e.message : "Przetwarzanie zbiorcze nie powiodło się.",
    };
  } finally {
    bulkRunning.value = false;
    await load();
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
          Ekstrakcja faktów z prozy przez LLM — pojedynczo lub dla całego vault naraz.
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

    <div class="bulk-panel">
      <div class="bulk-panel__row">
        <div>
          <span class="bulk-panel__label">Przetwarzanie zbiorcze</span>
          <p class="bulk-panel__hint">
            Analizuje tylko dokumenty nowe/zmienione od ostatniego przebiegu LLM.
            Jeden błąd nie przerywa reszty — dostaniesz raport co się nie udało.
          </p>
        </div>
        <div class="bulk-panel__buttons">
          <button
            class="btn btn--primary"
            :disabled="bulkRunning || !llmStatus?.active_provider"
            @click="runBulk(false)"
          >
            {{ bulkRunning ? "Przetwarzam…" : "Przetwórz nowe/zmienione" }}
          </button>
          <button
            class="btn"
            :disabled="bulkRunning || !llmStatus?.active_provider"
            title="Przetwarza WSZYSTKIE dokumenty od nowa, ignorując co już było zrobione"
            @click="runBulk(true)"
          >
            Przetwórz wszystko od nowa
          </button>
        </div>
      </div>

      <div v-if="bulkResult" class="bulk-result">
        <p v-if="bulkResult.error" class="banner banner--error">{{ bulkResult.error }}</p>
        <template v-else>
          <p class="bulk-result__summary">
            Przetworzono: {{ bulkResult.processed }} ·
            Pominięto (aktualne): {{ bulkResult.skipped_up_to_date }} ·
            Błędy: {{ bulkResult.failed?.length ?? 0 }}
            <template v-if="bulkResult.conflicts">
              · Nowe konflikty: {{ bulkResult.conflicts.created }}
            </template>
          </p>
          <ul v-if="bulkResult.failed?.length" class="bulk-errors">
            <li v-for="f in bulkResult.failed" :key="f.document_id" class="bulk-errors__item">
              <strong>{{ f.document }}</strong>: {{ f.error }}
            </li>
          </ul>
        </template>
      </div>
    </div>

    <p v-if="error" class="banner banner--error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Ładowanie…</p>
    <p v-else-if="documents.length === 0" class="muted">Brak dokumentów. Zsynchronizuj vault na Dashboardzie.</p>

    <ul v-else class="document-list">
      <li v-for="doc in documents" :key="doc.id" class="document-card">
        <div class="document-card__row">
          <div class="document-card__info">
            <RouterLink :to="`/documents/${doc.id}`" class="document-card__title">
              {{ doc.title }}
              <span v-if="doc.needs_llm_processing" class="pending-dot" title="Wymaga przetworzenia LLM" />
            </RouterLink>
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

    <Pagination :page="page" :total-pages="totalPages" :total="total" @change="changePage" />
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

.bulk-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  margin-bottom: 20px;
}

.bulk-panel__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.bulk-panel__label {
  font-size: 13px;
  font-weight: 600;
}

.bulk-panel__hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: 4px 0 0;
  max-width: 480px;
}

.bulk-panel__buttons {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.btn--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #14161d;
}

.bulk-result {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-soft);
}

.bulk-result__summary {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.bulk-errors {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bulk-errors__item {
  font-size: 12px;
  color: var(--severity-high);
  background: var(--severity-high-soft);
  border-radius: var(--radius);
  padding: 6px 10px;
}

.pending-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  margin-left: 6px;
  vertical-align: middle;
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
  color: var(--text);
  text-decoration: none;
}

.document-card__title:hover {
  color: var(--accent-strong);
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
