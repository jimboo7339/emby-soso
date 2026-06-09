import { createRouter, createWebHistory } from "vue-router";
import DashboardView from "@/views/DashboardView.vue";
import TasksView from "@/views/TasksView.vue";
import SettingsView from "@/views/SettingsView.vue";
import MediaWallView from "@/views/MediaWallView.vue";
import MediaListView from "@/views/MediaListView.vue";
import MediaDetailView from "@/views/MediaDetailView.vue";
import LoginView from "@/views/LoginView.vue";
import { useAuthStore } from "@/stores/auth";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView, meta: { public: true } },
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

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.ready) {
    await auth.initialize();
  }

  if (to.meta.public) {
    if (to.name === "login" && auth.isLoggedIn) {
      return { path: (to.query.redirect as string) || "/" };
    }
    return true;
  }

  if (!auth.isLoggedIn) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  return true;
});
