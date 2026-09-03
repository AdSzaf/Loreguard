<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api, ApiError } from "../services/api";
import type {
  DocumentDetail,
  LlmExtractionResult,
  LlmStatus,
  SemanticCheckResult,
} from "../types/api";

const props = defineProps<{ id: string }>();

const doc = ref<DocumentDetail | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const llmStatus = ref<LlmStatus | null>(null);
const extracting = ref(false);
const extractionResult = ref<LlmExtractionResult | null>(null);

const checkingSemantic = ref(false);
const semanticResult = ref<SemanticCheckResult | null>(null);

async function load() {
  loading.value = true;
  error.value = null;

  try {
    const [detail, status] = await Promise.all([
      api.document(Number(props.id)),
      api.llmStatus(),
    ]);
    doc.value = detail;
    llmStatus.value = status;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Nie udało się pobrać dokumentu.";
  } finally {
    loading.value = false;
  }
}

async function extract() {
  if (!doc.value) return;

  extracting.value = true;
  extractionResult.value = null;

  try {
    extractionResult.value = await api.extractLlmFacts(doc.value.id);
  } catch (e) {
    extractionResult.value = {
      error: e instanceof ApiError ? e.message : "Ekstrakcja nie powiodła się.",
    };
  } finally {
    extracting.value = false;
    await load();
  }
}

async function checkSemantic() {
  if (!doc.value) return;

  checkingSemantic.value = true;
  semanticResult.value = null;

  try {
    semanticResult.value = await api.checkSemanticConflicts(doc.value.id);
  } catch (e) {
    semanticResult.value = {
      error: e instanceof ApiError ? e.message : "Sprawdzenie semantyczne nie powiodło się.",
    };
  } finally {
    checkingSemantic.value = false;
    await load();
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <p v-if="error" class="banner banner--error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Ładowanie…</p>

    <template v-else-if="doc">
      <header class="page__header">
        <div>
          <h1 class="page__title">
            {{ doc.title }}
            <span v-if="doc.needs_llm_processing" class="pending-dot" title="Wymaga przetworzenia LLM" /><span v-if="doc.needs_semantic_check" class="pending-dot pending-dot--semantic" title="Wymaga sprawdzenia semantycznego" />
          </h1>
          <p class="page__path mono">{{ doc.path }}</p>
        </div>

        <div class="page__actions">
          <button
            class="btn btn--primary"
            :disabled="extracting || !llmStatus?.active_provider"
            :title="!llmStatus?.active_provider ? 'Skonfiguruj ANTHROPIC_API_KEY lub GEMINI_API_KEY w .env' : ''"
            @click="extract"
          >
            {{ extracting ? "Analizuję…" : "Wyciągnij fakty (LLM)" }}
          </button>
          <button
            class="btn"
            :disabled="checkingSemantic || !llmStatus?.active_provider"
            :title="!llmStatus?.active_provider ? 'Skonfiguruj ANTHROPIC_API_KEY lub GEMINI_API_KEY w .env' : 'Szuka sprzeczności z podobnymi tematycznie dokumentami'"
            @click="checkSemantic"
          >
            {{ checkingSemantic ? "Sprawdzam…" : "Sprawdź semantycznie" }}
          </button>
        </div>
      </header>

      <div v-if="extractionResult" class="result">
        <p v-if="extractionResult.error" class="banner banner--error">{{ extractionResult.error }}</p>
        <p v-else class="result__summary">
          Znaleziono {{ extractionResult.facts_extracted ?? 0 }} fakt(ów).
          <template v-if="extractionResult.conflicts">
            Nowe konflikty: {{ extractionResult.conflicts.created }}.
          </template>
        </p>
      </div>

      <div v-if="semanticResult" class="result">
        <p v-if="semanticResult.error" class="banner banner--error">{{ semanticResult.error }}</p>
        <p v-else class="result__summary">
          Sprawdzono {{ semanticResult.checked_against ?? 0 }} podobnych dokumentów,
          znaleziono {{ semanticResult.conflicts_found ?? 0 }} konflikt(ów).
        </p>
      </div>

      <section class="panel">
        <h2 class="panel__title">Powiązane encje</h2>
        <p v-if="doc.entities.length === 0" class="muted">Brak.</p>
        <div v-else class="entity-chips">
          <RouterLink
            v-for="entity in doc.entities"
            :key="entity.id"
            :to="`/entities/${entity.id}`"
            class="entity-chip"
          >
            {{ entity.name }}
          </RouterLink>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Fakty</h2>
        <p v-if="doc.facts.length === 0" class="muted">Brak zapisanych faktów.</p>
        <table v-else class="facts-table">
          <tbody>
            <tr v-for="fact in doc.facts" :key="fact.id">
              <td class="facts-table__subject">{{ fact.subject }}</td>
              <td class="facts-table__predicate mono">{{ fact.predicate }}</td>
              <td>{{ fact.value }}</td>
              <td class="facts-table__source mono">
                {{ fact.source_type === "llm_prose" ? "LLM" : "frontmatter" }}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 780px;
}

.page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.page__actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.page__title {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  margin: 0 0 4px;
}

.page__path {
  font-size: 12px;
  color: var(--text-faint);
  margin: 0;
}

.pending-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  margin-left: 6px;
  vertical-align: middle;
}

.pending-dot--semantic {
  background: var(--severity-medium, #d9a441);
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
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.5;
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

.muted {
  color: var(--text-muted);
  font-size: 14px;
}

.result {
  margin-bottom: 20px;
}

.result__summary {
  font-size: 13px;
  color: var(--text-muted);
  background: var(--surface-raised);
  border-radius: var(--radius);
  padding: 8px 12px;
  margin: 0;
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

.entity-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-chip {
  font-size: 12px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 12px;
  color: var(--text);
  text-decoration: none;
}

.entity-chip:hover {
  border-color: var(--accent);
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

.facts-table__subject {
  color: var(--text-muted);
  white-space: nowrap;
}

.facts-table__predicate {
  color: var(--accent-strong);
  white-space: nowrap;
}

.facts-table__source {
  text-align: right;
  color: var(--text-faint);
  font-size: 11px;
  white-space: nowrap;
}
</style>
