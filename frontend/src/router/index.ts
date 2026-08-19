import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    name: "dashboard",
    component: () => import("../views/DashboardView.vue"),
  },
  {
    path: "/conflicts",
    name: "conflicts",
    component: () => import("../views/ConflictsView.vue"),
  },
  {
    path: "/entities",
    name: "entities",
    component: () => import("../views/EntitiesView.vue"),
  },
  {
    path: "/entities/:id",
    name: "entity-detail",
    component: () => import("../views/EntityDetailView.vue"),
    props: true,
  },
  {
    path: "/events",
    name: "events",
    component: () => import("../views/TimelineView.vue"),
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
