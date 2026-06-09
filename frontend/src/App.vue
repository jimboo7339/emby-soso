<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import {
  NBreadcrumb,
  NBreadcrumbItem,
  NButton,
  NConfigProvider,
  NDialogProvider,
  NLayout,
  NLayoutSider,
  NMenu,
  NMessageProvider,
  NSpin,
  zhCN,
  dateZhCN,
  type MenuOption,
} from "naive-ui";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const routeMap: Record<string, string> = {
  dashboard: "/",
  tasks: "/tasks",
  wall: "/wall",
  media: "/media",
  settings: "/settings",
};

const pageTitles: Record<string, string> = {
  dashboard: "仪表盘",
  tasks: "任务管理",
  wall: "海报墙",
  media: "媒体列表",
  settings: "系统设置",
  "media-detail": "媒体详情",
};

const menuOptions: MenuOption[] = [
  { label: "仪表盘", key: "dashboard" },
  { label: "任务管理", key: "tasks" },
  { label: "海报墙", key: "wall" },
  { label: "媒体列表", key: "media" },
  { label: "系统设置", key: "settings" },
];

const isLoginPage = computed(() => route.name === "login");

const activeKey = computed(() => {
  const name = route.name?.toString() ?? "dashboard";
  if (name === "media-detail") return "media";
  return name;
});

const breadcrumbs = computed(() => {
  const name = route.name?.toString() ?? "dashboard";
  if (name === "media-detail") {
    return [
      { label: "媒体列表", to: "/media" },
      { label: "媒体详情", to: null },
    ];
  }
  return [{ label: pageTitles[name] ?? name, to: null }];
});

function onMenuSelect(key: string) {
  const path = routeMap[key];
  if (path) {
    router.push(path);
  }
}

function goTo(path: string | null) {
  if (path) {
    router.push(path);
  }
}

async function handleLogout() {
  await auth.logout();
  await router.push("/login");
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <RouterView v-if="isLoginPage" />

        <NSpin v-else-if="!auth.ready" size="large" style="margin: 120px auto; display: block" />

        <NLayout v-else has-sider class="app-shell">
          <NLayoutSider bordered :width="220" collapse-mode="width" class="app-sider">
            <div class="app-brand">
              <span class="app-brand-text">{{ auth.appDisplayName }}</span>
            </div>
            <NMenu
              :value="activeKey"
              :options="menuOptions"
              @update:value="onMenuSelect"
            />
            <div v-if="auth.authEnabled" class="app-sider-footer">
              <div class="app-user">{{ auth.username }}</div>
              <NButton size="small" tertiary @click="handleLogout">退出登录</NButton>
            </div>
          </NLayoutSider>

          <div class="app-main">
            <header class="app-header">
              <NBreadcrumb>
                <NBreadcrumbItem
                  v-for="(item, index) in breadcrumbs"
                  :key="index"
                  :clickable="!!item.to"
                  @click="goTo(item.to)"
                >
                  {{ item.label }}
                </NBreadcrumbItem>
              </NBreadcrumb>
            </header>

            <main class="app-content">
              <RouterView />
            </main>
          </div>
        </NLayout>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style>
html,
body,
#app {
  margin: 0;
  padding: 0;
  height: 100%;
  overflow: hidden;
  background: #f5f7fa;
}

.app-shell {
  height: 100vh;
  overflow: hidden;
}

.app-shell > .n-layout-scroll-container {
  overflow: hidden !important;
}

.app-sider {
  height: 100vh !important;
  position: sticky;
  top: 0;
  left: 0;
  flex-shrink: 0;
}

.app-sider :deep(.n-layout-sider-scroll-container) {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.app-brand {
  flex-shrink: 0;
  padding: 20px 16px;
}

.app-brand-text {
  font-size: 18px;
  font-weight: 600;
  line-height: 1.4;
  word-break: break-word;
}

.app-sider :deep(.n-menu) {
  flex: 1;
  overflow-y: auto;
}

.app-sider-footer {
  flex-shrink: 0;
  padding: 12px 16px 16px;
  border-top: 1px solid #efeff5;
}

.app-user {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 8px;
}

.app-main {
  flex: 1;
  min-width: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f5f7fa;
}

.app-header {
  flex-shrink: 0;
  height: 56px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #efeff5;
  box-sizing: border-box;
  z-index: 10;
}

.app-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px;
  box-sizing: border-box;
}
</style>
