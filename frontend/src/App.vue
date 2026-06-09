<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import {
  NBreadcrumb,
  NBreadcrumbItem,
  NConfigProvider,
  NDialogProvider,
  NLayout,
  NLayoutSider,
  NMenu,
  NMessageProvider,
  zhCN,
  dateZhCN,
  type MenuOption,
} from "naive-ui";

const route = useRoute();
const router = useRouter();

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
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <NLayout has-sider class="app-shell">
          <NLayoutSider bordered :width="220" collapse-mode="width" class="app-sider">
            <div class="app-brand">
              <span class="app-brand-text">emby-soso</span>
            </div>
            <NMenu
              :value="activeKey"
              :options="menuOptions"
              @update:value="onMenuSelect"
            />
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
}

.app-sider :deep(.n-menu) {
  flex: 1;
  overflow-y: auto;
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
