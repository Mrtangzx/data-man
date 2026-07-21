<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  PhArrowClockwise,
  PhChatCircleDots,
  PhDownloadSimple,
  PhMicrophone,
  PhPaperPlaneTilt,
  PhPlay,
  PhSlidersHorizontal,
  PhStop,
  PhUploadSimple,
  PhUserFocus,
  PhVideoCamera,
  PhWaveform,
  PhX,
} from "@phosphor-icons/vue";
import { API_BASE, api, readableError } from "./api";
import { MockRealtimeClient } from "./realtime/MockRealtimeClient";
import type { Asset, ComputePlan, Deployment, LlmProvider, LlmProvidersResponse, SystemSummary, VideoJob } from "./types";

type View = "realtime" | "video" | "assets" | "settings";
type Transcript = { role: "user" | "assistant" | "system"; text: string };

const activeView = ref<View>("realtime");
const loading = ref(true);
const globalError = ref("");
const summary = ref<SystemSummary | null>(null);
const computePlan = ref<ComputePlan | null>(null);
const assets = ref<Asset[]>([]);
const deployments = ref<Deployment[]>([]);
const llmProviders = ref<LlmProvider[]>([]);
const activeProviderId = ref("env");
const selectedProviderId = ref("env");
const providerName = ref("");
const providerBaseUrl = ref("");
const providerModel = ref("");
const providerApiKey = ref("");
const providerSaving = ref(false);
const providerTesting = ref(false);
const providerMessage = ref("");
const providerError = ref("");

const realtimeClient = new MockRealtimeClient();
const realtimeState = ref<"idle" | "connecting" | "connected" | "listening" | "speaking" | "error">("idle");
const realtimeInput = ref("");
const realtimeError = ref("");
const transcripts = ref<Transcript[]>([
  { role: "system", text: "连接后可用文字或麦克风进行真实语言交流。" },
]);
let recognition: SpeechRecognition | null = null;

const script = ref("你好，我是 NOVA。这是一段由确定性 Mock 管线生成的示例视频，用于验证任务、进度、预览和下载流程。");
const selectedAvatar = ref("avatar_sample_v1");
const selectedVoice = ref("voice_sample_v1");
const selectedRender = ref("mock-render");
const motionProfile = ref<"steady" | "natural" | "expressive">("natural");
const videoJob = ref<VideoJob | null>(null);
const videoError = ref("");
const submittingVideo = ref(false);
let eventSource: EventSource | null = null;
let pollTimer: number | null = null;

const uploadKind = ref<"avatar" | "voice">("avatar");
const uploadFile = ref<File | null>(null);
const uploadResult = ref<string[]>([]);
const uploadError = ref("");
const uploading = ref(false);
const probing = ref("");

const navItems = [
  { id: "realtime" as const, label: "实时互动", icon: PhChatCircleDots },
  { id: "video" as const, label: "视频创作", icon: PhVideoCamera },
  { id: "assets" as const, label: "形象与声音", icon: PhUserFocus },
  { id: "settings" as const, label: "系统与算力", icon: PhSlidersHorizontal },
];

const avatarAssets = computed(() => assets.value.filter((asset) => asset.kind === "avatar"));
const voiceAssets = computed(() => assets.value.filter((asset) => asset.kind === "voice"));
const renderDeployments = computed(() => deployments.value.filter((item) => item.engine_kind === "render"));
const videoReady = computed(() => videoJob.value?.state === "succeeded" && Boolean(videoJob.value.download_url));
const selectedAvatarAsset = computed(() => avatarAssets.value.find((asset) => asset.id === selectedAvatar.value));
const selectedAvatarPreview = computed(() => {
  const asset = selectedAvatarAsset.value;
  return asset && asset.id !== "avatar_sample_v1" && asset.content_type?.startsWith("image/")
    ? `${API_BASE}/v1/assets/${asset.id}/content`
    : "";
});
const statusLabel = computed(() => {
  const labels: Record<string, string> = {
    idle: "未连接",
    connecting: "正在连接",
    connected: "可以交谈",
    listening: "正在聆听",
    speaking: "正在回答",
    error: "连接异常",
  };
  return labels[realtimeState.value];
});

async function loadWorkspace() {
  loading.value = true;
  globalError.value = "";
  try {
    const [nextSummary, nextComputePlan, nextAssets, nextDeployments, nextProviders] = await Promise.all([
      api<SystemSummary>("/system/summary"),
      api<ComputePlan>("/system/compute-plan"),
      api<Asset[]>("/assets"),
      api<Deployment[]>("/engine-deployments"),
      api<LlmProvidersResponse>("/llm/providers"),
    ]);
    summary.value = nextSummary;
    computePlan.value = nextComputePlan;
    assets.value = nextAssets;
    deployments.value = nextDeployments;
    llmProviders.value = nextProviders.providers;
    activeProviderId.value = nextProviders.active_provider_id;
    if (!llmProviders.value.some((provider) => provider.id === selectedProviderId.value)) {
      selectedProviderId.value = activeProviderId.value;
    }
    selectProvider(selectedProviderId.value);
    const realAvatar = avatarAssets.value.find((item) => item.id !== "avatar_sample_v1" && item.status === "ready");
    if (!avatarAssets.value.some((item) => item.id === selectedAvatar.value) || (selectedAvatar.value === "avatar_sample_v1" && realAvatar)) {
      selectedAvatar.value = realAvatar?.id || avatarAssets.value[0]?.id || "";
    }
    if (!voiceAssets.value.some((item) => item.id === selectedVoice.value)) selectedVoice.value = voiceAssets.value[0]?.id || "";
  } catch (error) {
    globalError.value = readableError(error);
  } finally {
    loading.value = false;
  }
}

function selectProvider(providerId: string) {
  selectedProviderId.value = providerId;
  const provider = llmProviders.value.find((item) => item.id === providerId);
  if (!provider) return;
  providerName.value = provider.name;
  providerBaseUrl.value = provider.base_url;
  providerModel.value = provider.model;
  providerApiKey.value = "";
  providerMessage.value = provider.configured ? `已配置：${provider.api_key_hint}` : "尚未配置 API key";
  providerError.value = "";
}

async function saveProvider(showMessage = true) {
  providerSaving.value = true;
  providerError.value = "";
  try {
    await api<LlmProvider>(`/llm/providers/${selectedProviderId.value}`, {
      method: "PUT",
      body: JSON.stringify({
        name: providerName.value,
        base_url: providerBaseUrl.value,
        model: providerModel.value,
        api_key: providerApiKey.value.trim() || null,
        active: true,
      }),
    });
    const refreshed = await api<LlmProvidersResponse>("/llm/providers");
    llmProviders.value = refreshed.providers;
    activeProviderId.value = refreshed.active_provider_id;
    if (showMessage) providerMessage.value = "已保存并启用，新的实时会话将使用此模型。";
    return true;
  } catch (error) {
    providerError.value = readableError(error);
    return false;
  } finally {
    providerSaving.value = false;
  }
}

async function testProviderConnection() {
  const saved = await saveProvider(false);
  if (!saved) return;
  providerTesting.value = true;
  providerError.value = "";
  try {
    const result = await api<{ reply: string; model: string }>(`/llm/providers/${selectedProviderId.value}/test`, { method: "POST" });
    providerMessage.value = `连接成功：${result.reply}（${result.model}）`;
  } catch (error) {
    providerError.value = readableError(error);
  } finally {
    providerTesting.value = false;
  }
}

async function connectRealtime() {
  realtimeError.value = "";
  realtimeState.value = "connecting";
  try {
    await realtimeClient.connect();
    realtimeState.value = "connected";
    transcripts.value.push({ role: "system", text: "会话已连接。现在由配置的真实语言模型回答。" });
  } catch (error) {
    realtimeState.value = "error";
    realtimeError.value = readableError(error);
  }
}

async function sendRealtimeText(text = realtimeInput.value) {
  const clean = text.trim();
  if (!clean || realtimeState.value === "idle" || realtimeState.value === "connecting") return;
  realtimeError.value = "";
  realtimeInput.value = "";
  transcripts.value.push({ role: "user", text: clean });
  realtimeState.value = "speaking";
  try {
    const turn = await realtimeClient.sendText(clean);
    transcripts.value.push({ role: "assistant", text: turn.assistant_text });
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(turn.assistant_text);
      utterance.lang = "zh-CN";
      utterance.rate = 1;
      utterance.onend = () => (realtimeState.value = "connected");
      window.speechSynthesis.speak(utterance);
    } else {
      realtimeState.value = "connected";
    }
  } catch (error) {
    realtimeState.value = "error";
    realtimeError.value = readableError(error);
  }
}

async function startMicrophone() {
  if (realtimeState.value === "idle") await connectRealtime();
  realtimeError.value = "";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      realtimeState.value = "connected";
      transcripts.value.push({ role: "system", text: "麦克风权限正常。当前浏览器不支持本地语音转文字，请使用文字输入验证后续链路。" });
      return;
    }
    recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const text = event.results[0]?.[0]?.transcript;
      if (text) void sendRealtimeText(text);
    };
    recognition.onerror = () => {
      realtimeState.value = "connected";
      realtimeError.value = "语音识别没有返回结果，可再次尝试或使用文字输入。";
    };
    recognition.onend = () => {
      if (realtimeState.value === "listening") realtimeState.value = "connected";
    };
    realtimeState.value = "listening";
    recognition.start();
  } catch (error) {
    realtimeState.value = "connected";
    realtimeError.value = error instanceof Error ? `无法使用麦克风：${error.message}` : "无法使用麦克风。";
  }
}

async function interruptRealtime() {
  recognition?.stop();
  window.speechSynthesis?.cancel();
  await realtimeClient.interrupt();
  realtimeState.value = "connected";
  transcripts.value.push({ role: "system", text: "已确认打断，当前回答已停止。" });
}

function applyJobSnapshot(event: Event) {
  const message = event as MessageEvent<string>;
  try {
    const payload = JSON.parse(message.data) as { snapshot?: VideoJob };
    if (payload.snapshot) {
      videoJob.value = payload.snapshot;
      if (["succeeded", "failed", "cancelled"].includes(payload.snapshot.state)) stopJobWatch();
    }
  } catch {
    void pollJob();
  }
}

function watchJob(job: VideoJob) {
  stopJobWatch();
  const url = `${API_BASE}/v1/video-jobs/${job.id}/events?after=${job.event_cursor}`;
  eventSource = new EventSource(url);
  ["job.queued", "job.leased", "job.progress", "job.succeeded", "job.cancel_requested", "job.cancelled"].forEach((name) =>
    eventSource?.addEventListener(name, applyJobSnapshot),
  );
  eventSource.onerror = () => {
    eventSource?.close();
    eventSource = null;
  };
  pollTimer = window.setInterval(() => void pollJob(), 1000);
}

async function pollJob() {
  if (!videoJob.value) return;
  try {
    videoJob.value = await api<VideoJob>(`/video-jobs/${videoJob.value.id}`);
    if (["succeeded", "failed", "cancelled"].includes(videoJob.value.state)) stopJobWatch();
  } catch (error) {
    videoError.value = readableError(error);
  }
}

function stopJobWatch() {
  eventSource?.close();
  eventSource = null;
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = null;
}

async function createVideo() {
  videoError.value = "";
  submittingVideo.value = true;
  try {
    const job = await api<VideoJob>("/video-jobs", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({
        script: script.value,
        avatar_version_id: selectedAvatar.value,
        voice_enrollment_id: selectedVoice.value,
        engine_deployment_id: selectedRender.value,
        output: { width: 1280, height: 720, fps: 25, container: "mp4", motion_profile: motionProfile.value },
      }),
    });
    videoJob.value = job;
    watchJob(job);
  } catch (error) {
    videoError.value = readableError(error);
  } finally {
    submittingVideo.value = false;
  }
}

async function cancelVideo() {
  if (!videoJob.value) return;
  videoJob.value = await api<VideoJob>(`/video-jobs/${videoJob.value.id}/cancel`, { method: "POST" });
}

function pickUpload(event: Event) {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0] || null;
}

async function uploadAsset() {
  if (!uploadFile.value) return;
  uploading.value = true;
  uploadError.value = "";
  uploadResult.value = [];
  try {
    const form = new FormData();
    form.append("file", uploadFile.value);
    const result = await api<{ checks: { label: string; message: string }[] }>(
      `/assets/preflight?kind=${uploadKind.value}`,
      { method: "POST", body: form },
    );
    uploadResult.value = result.checks.map((check) => `${check.label}：${check.message}`);
    uploadFile.value = null;
    await loadWorkspace();
  } catch (error) {
    uploadError.value = readableError(error);
  } finally {
    uploading.value = false;
  }
}

async function probe(deployment: Deployment) {
  probing.value = deployment.id;
  globalError.value = "";
  try {
    await api(`/engine-deployments/${deployment.id}/probe`, { method: "POST" });
    await loadWorkspace();
  } catch (error) {
    globalError.value = readableError(error);
  } finally {
    probing.value = "";
  }
}

onMounted(loadWorkspace);
onBeforeUnmount(() => {
  stopJobWatch();
  recognition?.stop();
  window.speechSynthesis?.cancel();
  void realtimeClient.disconnect();
});
</script>

<template>
  <div class="app-shell">
    <aside class="nav-rail" aria-label="主工作区">
      <button class="brand-mark" aria-label="NOVA 首页" @click="activeView = 'realtime'">N</button>
      <nav>
        <button
          v-for="item in navItems"
          :key="item.id"
          class="nav-button"
          :class="{ active: activeView === item.id }"
          :aria-current="activeView === item.id ? 'page' : undefined"
          :title="item.label"
          @click="activeView = item.id"
        >
          <component :is="item.icon" :size="22" weight="regular" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="profile-chip" title="本地单用户">本地</div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="workspace-label">NOVA 数字人工作室</p>
          <h1>{{ navItems.find((item) => item.id === activeView)?.label }}</h1>
        </div>
        <div class="runtime-state" :class="{ warn: summary?.mock_mode }">
          <span>{{ summary?.mock_mode ? "成片 Mock · 实时语言" : "真实引擎" }}</span>
          <small>{{ summary?.deployments_healthy ?? 0 }} 个引擎可用</small>
        </div>
      </header>

      <div v-if="globalError" class="notice error" role="alert">
        <span>{{ globalError }}</span>
        <button aria-label="关闭错误" @click="globalError = ''"><PhX :size="18" /></button>
      </div>
      <div v-if="loading" class="workspace-loading" aria-live="polite">
        <span></span><span></span><span></span>
        <p>正在读取工作区</p>
      </div>

      <section v-else-if="activeView === 'realtime'" class="realtime-layout">
        <div class="avatar-stage">
          <div class="stage-toolbar">
            <span class="semantic-state" :class="realtimeState">{{ statusLabel }}</span>
            <select v-model="selectedAvatar" aria-label="实时人物形象">
              <option v-for="asset in avatarAssets" :key="asset.id" :value="asset.id">{{ asset.name }}</option>
            </select>
          </div>
          <div class="avatar-visual" :class="realtimeState" aria-label="NOVA 示例数字人形象">
            <div v-if="selectedAvatarPreview" class="portrait-frame photo">
              <img :src="selectedAvatarPreview" :alt="selectedAvatarAsset?.name || '数字人物形象'" />
              <span class="photo-label">内部测试素材</span>
            </div>
            <div v-else class="portrait-frame">
              <div class="portrait-head">
                <span class="portrait-eye left"></span>
                <span class="portrait-eye right"></span>
                <span class="portrait-mouth"></span>
              </div>
              <div class="portrait-shoulders"></div>
            </div>
            <div v-if="realtimeState === 'speaking' || realtimeState === 'listening'" class="voice-bars" aria-hidden="true">
              <span v-for="n in 7" :key="n" :style="{ '--delay': `${n * 60}ms` }"></span>
            </div>
          </div>
          <div class="stage-controls">
            <button v-if="realtimeState === 'idle' || realtimeState === 'error'" class="primary" @click="connectRealtime">
              <PhPlay :size="18" weight="fill" /> 开始会话
            </button>
            <template v-else>
              <button class="icon-action" :class="{ active: realtimeState === 'listening' }" title="使用麦克风" @click="startMicrophone">
                <PhMicrophone :size="21" />
              </button>
              <button class="danger-action" @click="interruptRealtime"><PhStop :size="18" weight="fill" /> 打断</button>
            </template>
          </div>
          <p v-if="realtimeError" class="inline-error" role="alert">{{ realtimeError }}</p>
        </div>

        <aside class="transcript-panel">
          <div class="panel-heading">
            <div><PhWaveform :size="18" /><span>实时字幕</span></div>
            <small>{{ transcripts.length }} 条</small>
          </div>
          <div class="transcript-list" aria-live="polite">
            <div v-for="(line, index) in transcripts" :key="index" class="transcript" :class="line.role">
              <span>{{ line.role === "assistant" ? "NOVA" : line.role === "user" ? "你" : "系统" }}</span>
              <p>{{ line.text }}</p>
            </div>
          </div>
          <form class="composer" @submit.prevent="sendRealtimeText()">
            <label for="realtime-message">输入消息</label>
            <div>
              <textarea id="realtime-message" v-model="realtimeInput" rows="2" placeholder="例如：介绍一下你能做什么" @keydown.ctrl.enter="sendRealtimeText()"></textarea>
              <button type="submit" :disabled="!realtimeInput.trim() || realtimeState === 'idle'" aria-label="发送消息">
                <PhPaperPlaneTilt :size="19" weight="fill" />
              </button>
            </div>
            <small>Ctrl + Enter 发送</small>
          </form>
        </aside>
      </section>

      <section v-else-if="activeView === 'video'" class="video-layout">
        <form class="creation-form" @submit.prevent="createVideo">
          <div class="section-intro">
            <h2>从文案生成成片</h2>
            <p>图片将由动作引擎生成眨眼、呼吸和头部动作，再由口型引擎对齐语音。Mock 只验证任务协议，不代表生成质量。</p>
          </div>
          <label for="video-script">视频文案</label>
          <textarea id="video-script" v-model="script" rows="8" maxlength="10000"></textarea>
          <span class="field-count">{{ script.length }} / 10000</span>
          <div class="form-grid">
            <div>
              <label for="avatar-select">人物形象</label>
              <select id="avatar-select" v-model="selectedAvatar">
                <option v-for="asset in avatarAssets" :key="asset.id" :value="asset.id">{{ asset.name }}</option>
              </select>
            </div>
            <div>
              <label for="voice-select">声音</label>
              <select id="voice-select" v-model="selectedVoice">
                <option v-for="asset in voiceAssets" :key="asset.id" :value="asset.id">{{ asset.name }}</option>
              </select>
            </div>
            <div>
              <label for="engine-select">成片引擎</label>
              <select id="engine-select" v-model="selectedRender">
                <option v-for="deployment in renderDeployments" :key="deployment.id" :value="deployment.id">{{ deployment.name }}</option>
              </select>
            </div>
            <div>
              <label for="motion-select">动作风格</label>
              <select id="motion-select" v-model="motionProfile">
                <option value="steady">克制稳定</option>
                <option value="natural">自然交流</option>
                <option value="expressive">富有表现力</option>
              </select>
            </div>
            <div>
              <label>输出规格</label>
              <div class="fixed-spec">1280 × 720 <span>25 FPS / MP4</span></div>
            </div>
          </div>
          <button class="primary wide" type="submit" :disabled="submittingVideo || !script.trim()">
            <PhVideoCamera :size="19" /> {{ submittingVideo ? "正在提交" : "生成示例视频" }}
          </button>
          <p v-if="videoError" class="inline-error" role="alert">{{ videoError }}</p>
        </form>

        <div class="render-monitor">
          <div v-if="!videoJob" class="empty-state">
            <PhVideoCamera :size="42" weight="thin" />
            <h3>等待第一次生成</h3>
            <p>提交后，任务状态与成片预览会显示在这里。</p>
          </div>
          <template v-else>
            <div class="monitor-heading">
              <div>
                <span class="job-state">{{ videoJob.state }}</span>
                <h3>{{ videoJob.stage }}</h3>
              </div>
              <strong>{{ videoJob.progress ?? 0 }}%</strong>
            </div>
            <div class="progress-track" :aria-label="`生成进度 ${videoJob.progress ?? 0}%`">
              <span :style="{ transform: `scaleX(${(videoJob.progress ?? 0) / 100})` }"></span>
            </div>
            <video v-if="videoReady" class="video-preview" controls :src="`${videoJob.download_url}`"></video>
            <div v-else class="processing-visual">
              <span></span><span></span><span></span>
              <p>{{ videoJob.state === "cancelled" ? "任务已取消" : "正在执行确定性成片管线" }}</p>
            </div>
            <div class="monitor-actions">
              <a v-if="videoReady" class="primary link-button" :href="videoJob.download_url || '#'" download>
                <PhDownloadSimple :size="18" /> 下载 MP4
              </a>
              <button v-if="!['succeeded', 'failed', 'cancelled'].includes(videoJob.state)" class="secondary" @click="cancelVideo">
                取消任务
              </button>
              <button class="secondary" @click="videoJob = null">新建任务</button>
            </div>
          </template>
        </div>
      </section>

      <section v-else-if="activeView === 'assets'" class="assets-layout">
        <div class="upload-panel">
          <div class="section-intro">
            <h2>添加人物或声音素材</h2>
            <p>这里只做安全大小和媒体类型预检。正式模型会再次检查清晰度、时长、口型和授权。</p>
          </div>
          <div class="segmented" role="group" aria-label="素材类型">
            <button :class="{ active: uploadKind === 'avatar' }" @click="uploadKind = 'avatar'">人物形象</button>
            <button :class="{ active: uploadKind === 'voice' }" @click="uploadKind = 'voice'">声音样本</button>
          </div>
          <label class="drop-zone" for="asset-file">
            <PhUploadSimple :size="28" />
            <strong>{{ uploadFile?.name || "选择本地媒体文件" }}</strong>
            <span>最大 25 MB，开发期只保存到本地对象目录</span>
          </label>
          <input id="asset-file" class="visually-hidden" type="file" :accept="uploadKind === 'avatar' ? 'image/*,video/*' : 'audio/*,video/*'" @change="pickUpload" />
          <button class="primary wide" :disabled="!uploadFile || uploading" @click="uploadAsset">
            {{ uploading ? "正在预检" : "上传并预检" }}
          </button>
          <div v-if="uploadResult.length" class="check-results">
            <p v-for="result in uploadResult" :key="result">{{ result }}</p>
          </div>
          <p v-if="uploadError" class="inline-error">{{ uploadError }}</p>
        </div>
        <div class="asset-library">
          <div class="library-heading">
            <h2>素材库</h2>
            <span>{{ assets.length }} 项</span>
          </div>
          <div v-if="!assets.length" class="empty-state compact"><p>还没有素材，请先上传。</p></div>
          <article v-for="asset in assets" :key="asset.id" class="asset-row">
            <div class="asset-symbol" :class="asset.kind"><PhUserFocus v-if="asset.kind === 'avatar'" :size="21" /><PhWaveform v-else :size="21" /></div>
            <div>
              <h3>{{ asset.name }}</h3>
              <p>{{ asset.source_name || "本地素材" }}</p>
            </div>
            <div class="asset-meta"><span>{{ asset.engine }}</span><strong>{{ asset.status }}</strong></div>
          </article>
        </div>
      </section>

      <section v-else class="settings-layout">
        <div class="system-summary">
          <div class="section-intro">
            <h2>控制平面状态</h2>
            <p>视频成片在开发环境仍使用 Mock；实时交流会调用后端配置的真实语言模型，未配置时会明确提示。</p>
          </div>
          <dl>
            <div><dt>运行 Profile</dt><dd>{{ summary?.profile }}</dd></div>
            <div><dt>可用素材</dt><dd>{{ summary?.assets_ready }}</dd></div>
            <div><dt>健康引擎</dt><dd>{{ summary?.deployments_healthy }}</dd></div>
            <div><dt>上游锁定</dt><dd>{{ summary?.upstream_gate_resolved ? "已完成" : "待完成" }}</dd></div>
          </dl>
          <div class="provider-config">
            <div class="library-heading">
              <div>
                <h2>语言模型供应商</h2>
                <p>支持 Kimi、OpenAI、DeepSeek、通义及其他 OpenAI-compatible 服务。</p>
              </div>
              <span class="provider-status">{{ activeProviderId === selectedProviderId ? "当前使用" : "待启用" }}</span>
            </div>
            <label>供应商
              <select v-model="selectedProviderId" @change="selectProvider(selectedProviderId)">
                <option v-for="provider in llmProviders" :key="provider.id" :value="provider.id">
                  {{ provider.name }}{{ provider.configured ? " · 已配置" : " · 未配置" }}
                </option>
              </select>
            </label>
            <div class="form-grid">
              <label>显示名称<input v-model="providerName" type="text" placeholder="例如：公司 Kimi" /></label>
              <label>模型名称<input v-model="providerModel" type="text" placeholder="例如：kimi-k2.6" /></label>
            </div>
            <label>Base URL<input v-model="providerBaseUrl" type="url" placeholder="https://api.example.com/v1" /></label>
            <label>API key<input v-model="providerApiKey" type="password" autocomplete="new-password" placeholder="只在此处输入，不会回显" /></label>
            <div class="provider-actions">
              <button class="primary" :disabled="providerSaving || providerTesting" @click="saveProvider()">
                {{ providerSaving ? "保存中" : "保存并启用" }}
              </button>
              <button class="secondary" :disabled="providerSaving || providerTesting" @click="testProviderConnection">
                {{ providerTesting ? "测试中" : "保存并测试" }}
              </button>
            </div>
            <p v-if="providerMessage" class="inline-success">{{ providerMessage }}</p>
            <p v-if="providerError" class="inline-error">{{ providerError }}</p>
            <small class="provider-note">API key 只在后端进程内使用，不会返回给页面。页面配置在 API 进程重启后恢复为环境变量配置。</small>
          </div>
        </div>
        <div class="deployment-list">
          <div class="library-heading"><h2>算力与引擎</h2><button class="text-action" @click="loadWorkspace"><PhArrowClockwise :size="17" /> 刷新</button></div>
          <div v-if="computePlan" class="compute-plan">
            <div class="compute-plan-heading">
              <span>当前最低成本建议</span>
              <strong>{{ computePlan.provider }} / {{ computePlan.gpu }}</strong>
            </div>
            <div class="compute-plan-metrics">
              <div><small>闲置费用</small><b>{{ computePlan.scale_to_zero ? "$0" : "持续计费" }}</b></div>
              <div><small>GPU 单价</small><b>${{ computePlan.rate_usd_per_hour.toFixed(2) }}/小时</b></div>
              <div><small>社区资源</small><b>{{ computePlan.free_quota_label }}</b></div>
              <div><small>额度内成片</small><b>${{ computePlan.estimated_gpu_cost_per_output_minute_usd.toFixed(2) }}</b></div>
            </div>
            <p>{{ computePlan.next_action }}</p>
            <small>{{ computePlan.estimate_assumption }} 价格核对：{{ computePlan.checked_at }}</small>
          </div>
          <article v-for="deployment in deployments" :key="deployment.id" class="deployment-row">
            <div>
              <span class="engine-kind">{{ deployment.engine_kind }}</span>
              <h3>{{ deployment.name }}</h3>
              <p>{{ deployment.target_kind }} / {{ deployment.revision.adapter_type }}</p>
            </div>
            <div class="deployment-health">
              <strong :class="deployment.observation?.healthy ? 'healthy' : 'unhealthy'">{{ deployment.observation?.healthy ? "健康" : "异常" }}</strong>
              <span>{{ deployment.observation?.latency_ms ?? "-" }} ms</span>
            </div>
            <button class="secondary" :disabled="probing === deployment.id" @click="probe(deployment)">
              {{ probing === deployment.id ? "检查中" : "执行探测" }}
            </button>
          </article>
          <div class="operator-note">
            <h3>真实算力接入</h3>
            <p>本机不要求 NVIDIA 显卡。实时语言模型通过后端服务调用；低频真实成片仍使用按秒远端 Worker，避免本机常驻 GPU。</p>
            <code>.\nova.ps1 target list</code>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
