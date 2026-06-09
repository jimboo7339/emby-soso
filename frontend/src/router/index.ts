import { createRouter, createWebHistory } from "vue-router";
import DashboardView from "@/views/DashboardView.vue";
import TasksView from "@/views/TasksView.vue";
import SettingsView from "@/views/SettingsView.vue";
import MediaWallView from "@/views/MediaWallView.vue";
import MediaListView from "@/views/MediaListView.vue";
import MediaDetailView from "@/views/MediaDetailView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardView },
    { path: "/tasks", name: "tasks", component: TasksView },
    { path: "/settings", name: "settings", component: SettingsView },
    { path: "/wall", name: "wall", component: MediaWallView },
    { path: "/media", name: "media", component: MediaListView },
    {
      path: "/media/:id",
      name: "media-detail",
      component: MediaDetailView,
      props: true,
    },
  ],
});
