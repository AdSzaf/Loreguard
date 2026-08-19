<script setup lang="ts">
import { computed } from "vue";
import type { ConflictStatus } from "../types/api";

const props = defineProps<{ status: ConflictStatus }>();

const label = computed(
  () =>
    ({
      open: "Otwarty",
      confirmed: "Potwierdzony",
      dismissed: "Odrzucony",
      explained: "Wyjaśniony",
    })[props.status],
);
</script>

<template>
  <span class="status" :class="`status--${status}`">{{ label }}</span>
</template>

<style scoped>
.status {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid currentColor;
}

.status--open {
  color: var(--status-open);
}
.status--confirmed {
  color: var(--status-confirmed);
}
.status--dismissed {
  color: var(--status-dismissed);
}
.status--explained {
  color: var(--status-explained);
}
</style>
