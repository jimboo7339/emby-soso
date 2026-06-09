import { defineStore } from "pinia";
import {
  authBootstrap,
  authLogin,
  authLogout,
  authMe,
  fetchSettings,
  updateSettings,
} from "@/api";

const TOKEN_KEY = "emby_soso_token";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    ready: false,
    authEnabled: true,
    authenticated: false,
    username: null as string | null,
    appDisplayName: "emby-soso",
    token: localStorage.getItem(TOKEN_KEY),
  }),

  getters: {
    isLoggedIn: (state) => !state.authEnabled || state.authenticated,
  },

  actions: {
    setToken(token: string | null) {
      this.token = token;
      if (token) {
        localStorage.setItem(TOKEN_KEY, token);
      } else {
        localStorage.removeItem(TOKEN_KEY);
      }
    },

    async initialize() {
      if (this.ready) {
        return;
      }
      try {
        const bootstrap = await authBootstrap();
        this.authEnabled = bootstrap.auth_enabled;
        this.appDisplayName = bootstrap.app_display_name;

        if (!this.authEnabled) {
          this.authenticated = true;
          this.username = null;
          return;
        }

        if (this.token) {
          try {
            const me = await authMe();
            this.authenticated = true;
            this.username = me.username;
            this.appDisplayName = me.app_display_name;
          } catch {
            this.setToken(null);
            this.authenticated = false;
            this.username = null;
          }
        }
      } finally {
        this.ready = true;
      }
    },

    async login(username: string, password: string) {
      const result = await authLogin(username, password);
      if (result.access_token) {
        this.setToken(result.access_token);
      }
      this.authenticated = true;
      this.username = result.username;
      this.appDisplayName = result.app_display_name;
    },

    async logout() {
      try {
        await authLogout();
      } finally {
        this.setToken(null);
        this.authenticated = false;
        this.username = null;
      }
    },

    async refreshDisplayName() {
      try {
        const settings = await fetchSettings();
        this.appDisplayName = settings.app_display_name;
      } catch {
        // ignore
      }
    },

    async saveDisplayName(name: string) {
      const data = await updateSettings({ app_display_name: name });
      this.appDisplayName = data.app_display_name;
    },
  },
});
