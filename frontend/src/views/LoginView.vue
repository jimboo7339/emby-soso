<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NCard, NForm, NFormItem, NInput, NSpace, useMessage } from "naive-ui";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const auth = useAuthStore();

const loading = ref(false);
const form = reactive({
  username: "",
  password: "",
});

onMounted(() => {
  if (auth.isLoggedIn) {
    void router.replace((route.query.redirect as string) || "/");
  }
});

async function handleLogin() {
  if (!form.username.trim() || !form.password) {
    message.warning("请输入用户名和密码");
    return;
  }
  loading.value = true;
  try {
    await auth.login(form.username.trim(), form.password);
    message.success("登录成功");
    await router.replace((route.query.redirect as string) || "/");
  } catch (e) {
    message.error(e instanceof Error ? e.message : "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <NCard class="login-card" :title="auth.appDisplayName">
      <p class="login-subtitle">请登录后继续使用</p>
      <NForm label-placement="top">
        <NFormItem label="用户名">
          <NInput v-model:value="form.username" placeholder="admin" @keyup.enter="handleLogin" />
        </NFormItem>
        <NFormItem label="密码">
          <NInput
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </NFormItem>
        <NSpace vertical size="large" style="width: 100%">
          <NButton type="primary" block :loading="loading" @click="handleLogin">登录</NButton>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #eef2ff 0%, #f5f7fa 45%, #e2e8f0 100%);
  padding: 24px;
  box-sizing: border-box;
}

.login-card {
  width: 100%;
  max-width: 420px;
}

.login-subtitle {
  margin: 0 0 20px;
  color: #64748b;
  font-size: 14px;
}
</style>
