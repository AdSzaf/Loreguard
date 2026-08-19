<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand__mark">◐</span>
        <span class="brand__name">LoreGuard</span>
      </div>

      <nav class="nav">
        <RouterLink to="/" class="nav__link" active-class="nav__link--active" exact-active-class="nav__link--active">
          Dashboard
        </RouterLink>
        <RouterLink to="/conflicts" class="nav__link" active-class="nav__link--active">
          Konflikty
        </RouterLink>
        <RouterLink to="/entities" class="nav__link" active-class="nav__link--active">
          Encje
        </RouterLink>
        <RouterLink to="/events" class="nav__link" active-class="nav__link--active">
          Oś czasu
        </RouterLink>
      </nav>

      <div class="sidebar__footer">
        <span class="mono">strażnik kanonu</span>
      </div>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: var(--sidebar-width);
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 24px 16px;
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 24px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-soft);
}

.brand__mark {
  font-size: 20px;
  color: var(--accent);
}

.brand__name {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 16px;
}

.nav__link {
  display: block;
  padding: 9px 12px;
  border-radius: var(--radius);
  color: var(--text-muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.12s ease, color 0.12s ease;
}

.nav__link:hover {
  background: var(--surface-raised);
  color: var(--text);
}

.nav__link--active {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.sidebar__footer {
  margin-top: auto;
  padding: 0 8px;
  font-size: 11px;
  color: var(--text-faint);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.content {
  flex: 1;
  min-width: 0;
  padding: 32px 40px;
}
</style>