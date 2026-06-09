<script setup lang="ts">
import { h, onMounted, onUnmounted, reactive, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSwitch,
  NSpin,
  NTag,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import {
  createTask,
  deleteTask,
  fetchSettings,
  fetchTaskRuns,
  fetchTasks,
  runTask,
  runTaskSync,
  type TaskItem,
  type TaskRun,
} from "@/api";

const message = useMessage();
const loading = ref(false);
const runningId = ref<string | null>(null);
const pollTimer = ref<number | null>(null);
const tasks = ref<TaskItem[]>([]);
const lastRuns = ref<Record<string, TaskRun | undefined>>({});

const form = reactive({
  name: "",
  source_path: "",
  library_path: "",
  cron_expr: "0 */6 * * *",
  task_type: "scrape_incremental",
  enabled: true,
});

const pathHint = ref("");

const taskTypeOptions = [
  { label: "增量刮削（扫描+整理+刮削）", value: "scrape_incremental" },
  { label: "全量刮削", value: "scrape_full" },
  { label: "仅扫描", value: "scan_only" },
  { label: "仅整理", value: "organize_only" },
];

function runStatusType(status: string) {
  if (status === "success") return "success";
  if (status === "running") return "info";
  return "error";
}

function runStatusLabel(status: string) {
  if (status === "running") return "运行中";
  if (status === "success") return "成功";
  if (status === "failed") return "失败";
  return status;
}

function formatRunMessage(run: TaskRun) {
  if (run.message) return run.message;
  if (run.status === "running") return "执行中，请稍候…（刮削大量剧集可能需数分钟）";
  return "";
}

const columns: DataTableColumns<TaskItem> = [
  { title: "名称", key: "name" },
  { title: "源路径", key: "source_path", ellipsis: { tooltip: true } },
  { title: "库路径", key: "library_path", ellipsis: { tooltip: true } },
  { title: "Cron", key: "cron_expr" },
  {
    title: "类型",
    key: "task_type",
    render: (row) => taskTypeOptions.find((o) => o.value === row.task_type)?.label ?? row.task_type,
  },
  {
    title: "上次运行",
    key: "last_run",
    render: (row) => {
      const run = lastRuns.value[row.id];
      if (!run) return "-";
      return h("div", { style: "max-width: 280px" }, [
        h(
          NTag,
          { size: "small", type: runStatusType(run.status), style: "margin-bottom: 4px" },
          { default: () => runStatusLabel(run.status) }
        ),
        h(
          "div",
          { style: "font-size: 12px; color: #666; word-break: break-all" },
          formatRunMessage(run)
        ),
      ]);
    },
  },
  {
    title: "操作",
    key: "actions",
    render: (row) =>
      h(NSpace, {}, {
        default: () => [
          h(
            NButton,
            {
              size: "small",
              type: "primary",
              loading: runningId.value === row.id,
              onClick: () => handleRun(row.id, false),
            },
            { default: () => "后台运行" }
          ),
          h(
            NButton,
            {
              size: "small",
              loading: runningId.value === row.id,
              onClick: () => handleRun(row.id, true),
            },
            { default: () => "同步运行" }
          ),
          h(
            NButton,
            {
              size: "small",
              type: "error",
              tertiary: true,
              onClick: () => handleDelete(row.id),
            },
            { default: () => "删除" }
          ),
        ],
      }),
  },
];

async function loadDefaults() {
  try {
    const settings = await fetchSettings();
    if (!form.source_path) {
      form.source_path = settings.data_source_root;
    }
    if (!form.library_path) {
      form.library_path = settings.data_library_root;
    }
    pathHint.value = `环境默认源目录: ${settings.data_source_root}，影视库: ${settings.data_library_root}`;
    if (!settings.tmdb_api_key_set) {
      message.warning("请先在系统设置中配置 TMDB API Key，否则无法自动匹配和刮削");
    }
  } catch {
    // ignore
  }
}

async function loadTasks() {
  loading.value = true;
  try {
    tasks.value = await fetchTasks();
    const runs = await Promise.all(tasks.value.map((t) => fetchTaskRuns(t.id)));
    tasks.value.forEach((t, i) => {
      lastRuns.value[t.id] = runs[i]?.[0];
    });
    syncTaskPolling();
  } catch (e) {
    message.error(e instanceof Error ? e.message : "加载任务失败");
  } finally {
    loading.value = false;
  }
}

function hasRunningTask() {
  return Object.values(lastRuns.value).some((run) => run?.status === "running");
}

function syncTaskPolling() {
  if (hasRunningTask() && pollTimer.value == null) {
    pollTimer.value = window.setInterval(() => {
      void loadTasksQuietly();
    }, 3000);
  } else if (!hasRunningTask() && pollTimer.value != null) {
    window.clearInterval(pollTimer.value);
    pollTimer.value = null;
  }
}

async function loadTasksQuietly() {
  try {
    tasks.value = await fetchTasks();
    const runs = await Promise.all(tasks.value.map((t) => fetchTaskRuns(t.id)));
    tasks.value.forEach((t, i) => {
      lastRuns.value[t.id] = runs[i]?.[0];
    });
    syncTaskPolling();
  } catch {
    // 轮询失败时静默，避免频繁弹窗
  }
}

async function handleCreate() {
  if (!form.name.trim()) {
    message.warning("请填写任务名称");
    return;
  }
  try {
    await createTask({
      ...form,
      use_global_scrape_config: true,
      config: { link_type: "auto" },
    });
    message.success("任务已创建");
    form.name = "";
    await loadTasks();
  } catch (e) {
    message.error(e instanceof Error ? e.message : "创建失败");
  }
}

async function handleRun(id: string, sync: boolean) {
  runningId.value = id;
  try {
    if (sync) {
      const run = await runTaskSync(id);
      message.success(`任务完成: ${run.status}`);
      if (run.message) message.info(run.message);
    } else {
      await runTask(id);
      message.success("任务已在后台启动");
    }
    await loadTasks();
  } catch (e) {
    message.error(e instanceof Error ? e.message : "运行失败");
  } finally {
    runningId.value = null;
  }
}

async function handleDelete(id: string) {
  try {
    await deleteTask(id);
    message.success("已删除");
    await loadTasks();
  } catch (e) {
    message.error(e instanceof Error ? e.message : "删除失败");
  }
}

onMounted(async () => {
  await loadDefaults();
  await loadTasks();
});

onUnmounted(() => {
  if (pollTimer.value != null) {
    window.clearInterval(pollTimer.value);
  }
});
</script>

<template>
  <NSpace vertical size="large">
    <NCard title="新建整理刮削任务">
      <NAlert v-if="pathHint" type="info" :title="pathHint" style="margin-bottom: 16px" />
      <NForm label-placement="left" label-width="100">
        <NFormItem label="任务名称">
          <NInput v-model:value="form.name" placeholder="例如：每日增量刮削" />
        </NFormItem>
        <NFormItem label="源路径">
          <NInput v-model:value="form.source_path" />
        </NFormItem>
        <NFormItem label="库路径">
          <NInput v-model:value="form.library_path" />
        </NFormItem>
        <NFormItem label="任务类型">
          <NSelect v-model:value="form.task_type" :options="taskTypeOptions" />
        </NFormItem>
        <NFormItem label="Cron 表达式">
          <NInput v-model:value="form.cron_expr" placeholder="0 */6 * * *" />
        </NFormItem>
        <NFormItem label="启用">
          <NSwitch v-model:value="form.enabled" />
        </NFormItem>
        <NButton type="primary" @click="handleCreate">创建任务</NButton>
      </NForm>
    </NCard>

    <NCard title="任务列表">
      <NSpin :show="loading">
        <NDataTable :columns="columns" :data="tasks" :bordered="false" />
      </NSpin>
    </NCard>
  </NSpace>
</template>
