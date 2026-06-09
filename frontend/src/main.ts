import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { api } from "./api";
import { router } from "./router";
import { useAuthStore } from "./stores/auth";

const TOKEN_KEY = "emby_soso_token";

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url = String(error.config?.url ?? "");
    if (
      status === 401 &&
      !url.includes("/auth/login") &&
      !url.includes("/auth/bootstrap")
    ) {
      localStorage.removeItem(TOKEN_KEY);
      const redirect = encodeURIComponent(window.location.pathname + window.location.search);
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = `/login?redirect=${redirect}`;
      }
    }
    return Promise.reject(error);
  }
);

async function bootstrap() {
  const app = createApp(App);
  const pinia = createPinia();
  app.use(pinia);

  const auth = useAuthStore();
  await auth.initialize();

  app.use(router);
  app.mount("#app");
}

void bootstrap();
