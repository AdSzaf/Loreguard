<script setup lang="ts">
import { computed } from "vue";
import type { ConflictSeverity } from "../types/api";

const props = defineProps<{ severity: ConflictSeverity }>();

const label = computed(
  () =>
    ({ low: "Niska", medium: "Średnia", high: "Wysoka" })[props.severity],
);
</script>

<template>
  <span class="badge" :class="`badge--${severity}`">
    <span class="badge__dot" />
    {{ label }}
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 3px 10px 3px 8px;
  border-radius: 999px;
  white-space: nowrap;
}

.badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.badge--high {
  background: var(--severity-high-soft);
  color: var(--severity-high);
}
.badge--high .badge__dot {
  background: var(--severity-high);
}

.badge--medium {
  background: var(--severity-medium-soft);
  color: var(--severity-medium);
}
.badge--medium .badge__dot {
  background: var(--severity-medium);
}

.badge--low {
  background: var(--severity-low-soft);
  color: var(--severity-low);
}
.badge--low .badge__dot {
  background: var(--severity-low);
}
</style>
