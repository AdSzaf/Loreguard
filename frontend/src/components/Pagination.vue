<script setup lang="ts">
defineProps<{
  page: number;
  totalPages: number;
  total: number;
}>();

const emit = defineEmits<{
  (e: "change", page: number): void;
}>();
</script>

<template>
  <div v-if="totalPages > 1" class="pagination">
    <button
      class="pagination__btn"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      ← Poprzednia
    </button>
    <span class="pagination__info">
      Strona {{ page }} / {{ totalPages }} ({{ total }} pozycji)
    </span>
    <button
      class="pagination__btn"
      :disabled="page >= totalPages"
      @click="emit('change', page + 1)"
    >
      Następna →
    </button>
  </div>
</template>

<style scoped>
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-soft);
}

.pagination__btn {
  font-size: 13px;
  padding: 7px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--text);
  cursor: pointer;
}

.pagination__btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.pagination__info {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
