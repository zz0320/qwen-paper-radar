<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api, todayLocal } from "./api";
import KeywordPanel from "./components/KeywordPanel.vue";
import FilterPanel from "./components/FilterPanel.vue";
import SectionSummary from "./components/SectionSummary.vue";
import PaperCard from "./components/PaperCard.vue";
import RichText from "./components/RichText.vue";

const defaultQwenBaseUrl = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const defaultQwenModel = "qwen-plus";

const settings = ref({ keywords: [], maxResults: 100 });
const sections = ref([]);
const qwen = ref({ configured: false, locked: false, editable: true, source: "none", model: "", baseUrl: "" });
const arxivMeta = ref({ defaultDate: todayLocal(), latestAvailableDate: todayLocal(), cooldown: null });
const paths = ref({ cache: "", library: "" });

const selectedDate = ref(todayLocal());
const activeSection = ref("all");
const papers = ref([]);
const library = ref({});
const counts = ref({});
const signature = ref("");
const arxivCooldown = ref(null);
const submittedDateRange = ref(null);
const sectionSummary = ref(null);
const paperSummaries = ref({});
const papersBusy = ref(false);
const sectionSummaryLoading = ref(false);
const paperLoading = reactive({});
const status = reactive({ text: "等待加载", type: "" });
const message = ref("");
const toast = reactive({ visible: false, text: "", actionLabel: "", action: null });
const qwenBusy = ref(false);
const qwenPanelMessage = ref("");
const qwenPanelError = ref("");
const qwenDraft = reactive({
  apiKey: "",
  model: defaultQwenModel,
  baseUrl: defaultQwenBaseUrl,
});

const filters = ref({
  search: "",
  sort: "date_desc",
  favoriteOnly: false,
  status: "",
});

const activeSectionObject = computed(() => {
  return sections.value.find((item) => item.id === activeSection.value) || sections.value[0] || {
    id: "all",
    label: "日期总览",
    description: "",
  };
});

const categorySections = computed(() => sections.value.filter((item) => item.id !== "all"));

const sectionLabelMap = computed(() => {
  return Object.fromEntries(sections.value.map((item) => [item.id, item.label]));
});

const dashboardCards = computed(() =>
  categorySections.value.map((section) => ({
    label: section.label,
    value: counts.value[section.id] ?? 0,
    tone: section.id,
  })),
);

const briefThemes = computed(() => {
  const keywordThemes = (settings.value.keywords || []).slice(0, 4);
  return [activeSectionObject.value.label, ...keywordThemes].filter(Boolean).slice(0, 5);
});

const briefText = computed(() => {
  return sectionSummary.value?.summary?.headline || status.text || "选择日期和关键词，加载本地 arXiv 论文池。";
});

const paperSummaryCount = computed(() => Object.keys(paperSummaries.value || {}).length);

const sectionSummaryStatus = computed(() => {
  if (sectionSummaryLoading.value) return "Qwen 生成中";
  if (sectionSummary.value?.summary) return "已生成";
  return "未生成";
});

const arxivCooldownText = computed(() => {
  if (!arxivCooldown.value) return "";
  const minutes = Math.max(1, Math.ceil((arxivCooldown.value.remainingSeconds || 0) / 60));
  return `arXiv 冷却中，约 ${minutes} 分钟后再试`;
});

const submittedRangeText = computed(() => {
  if (!submittedDateRange.value?.startUtc || !submittedDateRange.value?.endUtc) return "";
  const format = (value) => `${value.slice(4, 6)}/${value.slice(6, 8)} ${value.slice(8, 10)}:${value.slice(10, 12)}`;
  return `北京时间自然日 · UTC ${format(submittedDateRange.value.startUtc)}-${format(submittedDateRange.value.endUtc)}`;
});

const filteredPapers = computed(() => {
  const query = filters.value.search.trim().toLowerCase();
  let rows = papers.value.filter((paper) => {
    const entry = entryFor(paper.id);
    if (filters.value.favoriteOnly && !entry.favorite) return false;
    if (filters.value.status && entry.status !== filters.value.status) return false;
    if (!query) return true;
    return [paper.title, paper.abstract, (paper.authors || []).join(" "), (paper.categories || []).join(" "), (paper.matchedKeywords || []).join(" ")]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });

  rows = [...rows].sort((a, b) => {
    if (filters.value.sort === "score_desc") return (b.relevanceScore || 0) - (a.relevanceScore || 0);
    if (filters.value.sort === "title_asc") return a.title.localeCompare(b.title);
    if (filters.value.sort === "favorite_first") {
      const favoriteDelta = Number(Boolean(entryFor(b.id).favorite)) - Number(Boolean(entryFor(a.id).favorite));
      if (favoriteDelta !== 0) return favoriteDelta;
    }
    return String(b.published || "").localeCompare(String(a.published || ""));
  });
  return rows;
});

const categoryOverview = computed(() => {
  return categorySections.value
    .map((section) => {
      const rows = papers.value.filter((paper) => (paper.sections || []).includes(section.id));
      return {
        ...section,
        count: rows.length,
        topPapers: rows.slice(0, 3).map((paper) => paper.title),
      };
    })
    .filter((group) => group.count > 0);
});

const categoryInsightMap = computed(() => {
  const map = {};
  for (const item of categoryOverview.value) {
    map[item.id] = {
      id: item.id,
      label: item.label,
      count: item.count,
      summary: item.description,
      highlights: item.topPapers || [],
      risks: [],
      generated: false,
    };
  }

  const qwenRows = sectionSummary.value?.summary?.category_summaries;
  if (Array.isArray(qwenRows)) {
    for (const item of qwenRows) {
      if (!item?.id) continue;
      map[item.id] = {
        ...(map[item.id] || {}),
        ...item,
        label: item.label || map[item.id]?.label || item.id,
        generated: true,
      };
    }
  }
  return map;
});

const paperGroupOrder = [
  "model_training",
  "data_collection",
  "manipulation",
  "embodiment_system",
  "reasoning_safety",
  "sim_eval_repro",
];

function primaryPaperSectionId(paper) {
  if (paper.primarySection) return paper.primarySection;
  const paperSections = paper.sections || [];
  return paperGroupOrder.find((sectionId) => paperSections.includes(sectionId)) || paperSections[0] || "other";
}

const groupedFilteredPapers = computed(() => {
  const map = new Map();
  for (const paper of filteredPapers.value) {
    const sectionId = primaryPaperSectionId(paper);
    if (!map.has(sectionId)) {
      map.set(sectionId, {
        id: sectionId,
        label: sectionLabelMap.value[sectionId] || "其他论文",
        insight: categoryInsightMap.value[sectionId] || null,
        papers: [],
      });
    }
    map.get(sectionId).papers.push(paper);
  }
  const orderedIds = [...paperGroupOrder, "other"];
  const ordered = orderedIds.map((id) => map.get(id)).filter(Boolean);
  const rest = [...map.values()].filter((group) => !orderedIds.includes(group.id));
  return [...ordered, ...rest];
});

function entryFor(paperId) {
  return {
    favorite: false,
    status: "unread",
    category: "",
    notes: "",
    ...(library.value[paperId] || {}),
  };
}

function setStatus(text, type = "") {
  status.text = text;
  status.type = type;
}

function showToast(text, actionLabel = "", action = null) {
  toast.visible = true;
  toast.text = text;
  toast.actionLabel = actionLabel;
  toast.action = action;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.visible = false;
  }, 9000);
}

async function copyText(text) {
  await navigator.clipboard.writeText(text);
  showToast("已复制 Markdown");
}

async function loadConfig() {
  const config = await api("/api/config");
  settings.value = config.settings;
  sections.value = config.sections;
  qwen.value = config.qwen;
  arxivMeta.value = config.arxiv || arxivMeta.value;
  arxivCooldown.value = config.arxiv?.cooldown || null;
  paths.value = config.paths;
  hydrateQwenDraft(config.qwen);
}

function hydrateQwenDraft(next = qwen.value) {
  qwenDraft.apiKey = "";
  qwenDraft.model = next?.model || defaultQwenModel;
  qwenDraft.baseUrl = next?.baseUrl || defaultQwenBaseUrl;
}

async function lockQwenConfig() {
  qwenBusy.value = true;
  qwenPanelError.value = "";
  qwenPanelMessage.value = "正在检测 Qwen API...";
  try {
    const result = await api("/api/qwen/config", {
      method: "POST",
      body: JSON.stringify({
        apiKey: qwenDraft.apiKey,
        model: qwenDraft.model,
        baseUrl: qwenDraft.baseUrl,
      }),
    });
    qwen.value = result.qwen;
    hydrateQwenDraft(result.qwen);
    qwenPanelMessage.value = `检测成功，已锁定：${result.qwen.model} ${result.qwen.keyPreview || ""}`;
    showToast("Qwen API 已检测并锁定");
  } catch (error) {
    qwenPanelError.value = error.message;
    qwenPanelMessage.value = "";
  } finally {
    qwenBusy.value = false;
  }
}

async function unlockQwenConfig() {
  qwenBusy.value = true;
  qwenPanelError.value = "";
  qwenPanelMessage.value = "正在解锁 Qwen 配置...";
  try {
    const result = await api("/api/qwen/unlock", { method: "POST", body: JSON.stringify({}) });
    qwen.value = result.qwen;
    hydrateQwenDraft(result.qwen);
    qwenPanelMessage.value = "已解锁，可重新输入并检测。";
  } catch (error) {
    qwenPanelError.value = error.message;
    qwenPanelMessage.value = "";
  } finally {
    qwenBusy.value = false;
  }
}

async function saveSettings(patch) {
  setStatus("正在保存设置", "loading");
  const result = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify(patch),
  });
  settings.value = result.settings;
  await loadPapers(false);
}

async function loadPapers(refresh = false) {
  if (papersBusy.value) return;
  papersBusy.value = true;
  const params = new URLSearchParams({
    date: selectedDate.value,
    section: activeSection.value,
    refresh: refresh ? "1" : "0",
  });
  setStatus(refresh ? `正在从 arXiv 加载 ${selectedDate.value}` : "正在读取本地日期论文池", "loading");
  message.value = "";
  try {
    const payload = await api(`/api/papers?${params}`);
    papers.value = payload.papers || [];
    library.value = payload.library || {};
    counts.value = payload.counts || {};
    signature.value = payload.signature || "";
    arxivCooldown.value = payload.arxivCooldown || null;
    submittedDateRange.value = payload.submittedDateRange || null;
    if (payload.latestAvailableDate) arxivMeta.value = { ...arxivMeta.value, latestAvailableDate: payload.latestAvailableDate };
    sectionSummary.value = payload.sectionSummary || null;
    paperSummaries.value = payload.paperSummaries || {};
    message.value = payload.error || payload.warning || "";
    if (payload.error) {
      setStatus(payload.error, "error");
      showToast(payload.error);
    } else if (payload.warning) {
      setStatus(payload.warning, "warning");
      showToast(payload.warning);
    } else {
      setStatus(`${payload.cached ? "本地缓存" : "arXiv"}：${payload.date}，${payload.papers.length} 篇，签名 ${payload.signature}`);
    }
  } catch (error) {
    papers.value = [];
    setStatus(error.message, "error");
    showToast(error.message);
  } finally {
    papersBusy.value = false;
  }
}

async function updateLibrary(paperId, patch) {
  const result = await api("/api/library", {
    method: "POST",
    body: JSON.stringify({ paperId, patch }),
  });
  library.value = { ...library.value, [paperId]: result.entry };
  showToast("本地阅读数据已保存");
}

async function runSectionSummary() {
  sectionSummaryLoading.value = true;
  try {
    const result = await api("/api/qwen/section", {
      method: "POST",
      body: JSON.stringify({ date: selectedDate.value, section: activeSection.value }),
    });
    if (result.status === "cached") {
      sectionSummary.value = result.summary;
      sectionSummaryLoading.value = false;
      showToast("已读取分类 Qwen 总结缓存");
      return;
    }
    pollJob(result.job.id, { kind: "section" });
  } catch (error) {
    showToast(error.message);
    sectionSummaryLoading.value = false;
  }
}

async function runPaperSummary(paperId) {
  paperLoading[paperId] = true;
  try {
    const result = await api("/api/qwen/paper", {
      method: "POST",
      body: JSON.stringify({ date: selectedDate.value, paperId }),
    });
    if (result.status === "cached") {
      paperSummaries.value = { ...paperSummaries.value, [paperId]: result.summary };
      showToast("已读取单篇 Qwen 摘要缓存");
      paperLoading[paperId] = false;
      return;
    }
    pollJob(result.job.id, { kind: "paper", paperId });
  } catch (error) {
    showToast(error.message);
    paperLoading[paperId] = false;
  }
}

function pollJob(jobId, meta) {
  const timer = window.setInterval(async () => {
    try {
      const job = await api(`/api/qwen/job?id=${encodeURIComponent(jobId)}`);
      if (job.status === "queued" || job.status === "running") return;
      window.clearInterval(timer);
      if (job.status === "done") {
        if (meta.kind === "section") {
          sectionSummary.value = job.result;
          sectionSummaryLoading.value = false;
          showToast("分类 Qwen 总结已完成", "刷新日期论文", () => loadPapers(false));
        } else {
          paperSummaries.value = { ...paperSummaries.value, [meta.paperId]: job.result };
          paperLoading[meta.paperId] = false;
          showToast("单篇 Qwen 摘要已完成", "刷新卡片", () => loadPapers(false));
        }
      } else {
        if (meta.kind === "section") sectionSummaryLoading.value = false;
        if (meta.kind === "paper") paperLoading[meta.paperId] = false;
        showToast(`Qwen 任务失败：${job.error || "未知错误"}`);
      }
    } catch (error) {
      window.clearInterval(timer);
      if (meta.kind === "section") sectionSummaryLoading.value = false;
      if (meta.kind === "paper") paperLoading[meta.paperId] = false;
      showToast(error.message);
    }
  }, 2500);
}

function copySectionMarkdown() {
  copyText(sectionSummary.value?.summary?.markdown || "尚未生成总结。");
}

onMounted(async () => {
  await loadConfig();
  await loadPapers(false);
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <img class="brand-logo" src="/logo.svg" width="44" height="44" alt="" />
        <div>
          <p class="eyebrow">Robotics / Embodied AI Reading Desk</p>
          <h1>具身智读</h1>
        </div>
      </div>
      <div class="status-row">
        <span class="status" :class="qwen.configured ? 'status-ok' : 'status-warn'">
          {{ qwen.configured ? `Qwen ${qwen.locked ? "已锁定" : "已保存"}` : "Qwen 未配置" }}
        </span>
        <span class="mode-badge">{{ signature || "keyword signature" }}</span>
      </div>
    </header>

    <section class="command-bar" aria-label="全局检索和日期">
      <div class="command-copy">
        <p class="section-label">查询窗口</p>
        <strong>{{ selectedDate }}</strong>
        <span>{{ submittedRangeText || "北京时间自然日" }}</span>
      </div>
      <label class="search-box">
        <span aria-hidden="true">⌕</span>
        <input v-model="filters.search" type="search" placeholder="搜索标题、作者、方法、摘要和笔记" autocomplete="off" />
      </label>
      <div class="date-control">
        <label class="field field-date">
          <span>日期</span>
          <input v-model="selectedDate" type="date" :disabled="papersBusy" @change="loadPapers(false)" />
        </label>
        <button class="primary-button" type="button" :disabled="papersBusy" @click="loadPapers(false)">
          {{ papersBusy ? "加载中" : "读取缓存" }}
        </button>
        <button class="ghost-button" type="button" :disabled="papersBusy || Boolean(arxivCooldown)" @click="loadPapers(true)">
          {{ papersBusy ? "加载中" : arxivCooldown ? "冷却中" : "加载 arXiv" }}
        </button>
      </div>
    </section>

    <section class="qwen-access" :class="{ 'is-locked': qwen.locked }" aria-label="Qwen API 接入">
      <div class="qwen-access-head">
        <div>
          <p class="section-label">摘要与翻译引擎</p>
          <h2>Qwen API</h2>
        </div>
        <span v-if="!qwen.locked" class="status" :class="qwen.configured ? 'status-ok' : 'status-warn'">
          {{ qwen.configured ? `${qwen.model} · ${qwen.keyPreview || qwen.source}` : "未接入" }}
        </span>
      </div>

      <div v-if="qwen.locked" class="qwen-locked">
        <div>
          <strong>已锁定，可生成总结和摘要翻译</strong>
          <span>{{ qwen.model }} · {{ qwen.baseUrl }} · {{ qwen.keyPreview || qwen.source }}</span>
        </div>
        <span class="status status-ok">{{ qwen.model }} · {{ qwen.keyPreview || qwen.source }}</span>
        <button class="ghost-button" type="button" :disabled="qwenBusy || !qwen.editable" @click="unlockQwenConfig">
          解锁重填
        </button>
      </div>

      <form v-else class="qwen-form" @submit.prevent="lockQwenConfig">
        <label class="field qwen-key-field">
          <span>API Key</span>
          <input
            v-model="qwenDraft.apiKey"
            type="password"
            autocomplete="off"
            :placeholder="qwen.configured ? '留空则使用已保存 key' : 'sk-...'"
            :disabled="qwenBusy || !qwen.editable"
          />
        </label>
        <label class="field">
          <span>模型</span>
          <input v-model="qwenDraft.model" type="text" :disabled="qwenBusy || !qwen.editable" />
        </label>
        <label class="field qwen-url-field">
          <span>Base URL</span>
          <input v-model="qwenDraft.baseUrl" type="url" :disabled="qwenBusy || !qwen.editable" />
        </label>
        <button class="primary-button" type="submit" :disabled="qwenBusy || !qwen.editable">
          {{ qwenBusy ? "检测中" : "检测并锁定" }}
        </button>
      </form>

      <p v-if="qwenPanelMessage" class="qwen-message">{{ qwenPanelMessage }}</p>
      <p v-if="qwenPanelError" class="qwen-error">{{ qwenPanelError }}</p>
      <p class="qwen-footnote">Key 只保存在本机 `.data/qwen.json`，前端不会回显完整密钥。</p>
    </section>

    <section class="workflow-panel" aria-label="日期论文工作流">
      <article class="workflow-card">
        <span class="workflow-step">01</span>
        <div>
          <p class="section-label">arXiv 数据拉取</p>
          <h2>日期论文池</h2>
          <p>{{ arxivCooldownText || `${selectedDate} · ${papers.length} 篇 · ${submittedRangeText || `签名 ${signature || "未生成"}`}` }}</p>
        </div>
        <div class="workflow-actions">
          <button class="primary-button" type="button" :disabled="papersBusy" @click="loadPapers(false)">
            {{ papersBusy ? "加载中" : "读取缓存" }}
          </button>
          <button class="ghost-button" type="button" :disabled="papersBusy || Boolean(arxivCooldown)" @click="loadPapers(true)">
            {{ papersBusy ? "加载中" : arxivCooldown ? "冷却中" : "加载 arXiv" }}
          </button>
        </div>
      </article>

      <article class="workflow-card">
        <span class="workflow-step">02</span>
        <div>
          <p class="section-label">选定日期总结</p>
          <h2>{{ activeSectionObject.label }}</h2>
          <p>{{ selectedDate }} · {{ sectionSummaryStatus }} · 按专业栈归类 {{ papers.length }} 篇</p>
        </div>
        <div class="workflow-actions">
          <button class="primary-button" type="button" :disabled="sectionSummaryLoading" @click="runSectionSummary">
            {{ sectionSummaryLoading ? "生成中" : "生成总结" }}
          </button>
          <button class="ghost-button" type="button" @click="copySectionMarkdown">复制</button>
        </div>
      </article>

      <article class="workflow-card">
        <span class="workflow-step">03</span>
        <div>
          <p class="section-label">单篇论文总结</p>
          <h2>论文卡片独立处理</h2>
          <p>已缓存 {{ paperSummaryCount }} 篇 · 总结与摘要翻译按卡片单独生成</p>
        </div>
        <div class="workflow-actions muted-action">在论文卡片内操作</div>
      </article>
    </section>

    <section class="brief-band">
      <div class="brief-copy">
        <p class="section-label">{{ activeSectionObject.label }}</p>
        <p class="brief-text">{{ briefText }}</p>
        <div class="theme-list" aria-label="当前主题">
          <span v-for="theme in briefThemes" :key="theme" class="theme">{{ theme }}</span>
        </div>
      </div>
      <div class="brief-stats" aria-label="统计">
        <div v-for="card in dashboardCards" :key="card.label">
          <span class="meta-label">{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
        </div>
      </div>
    </section>

    <main class="layout">
      <aside class="side-panel">
        <KeywordPanel v-if="settings" :settings="settings" @save="saveSettings" />
        <FilterPanel v-model="filters" />
        <section class="panel status-panel">
          <div class="panel-head">
            <h2>运行状态</h2>
            <span class="chip">{{ signature || "signature" }}</span>
          </div>
          <p>{{ qwen.configured ? `Qwen ${qwen.locked ? "已锁定" : "已保存"}：${qwen.model}` : "Qwen 未配置：请在前台接入面板检测并锁定" }}</p>
          <p :class="status.type">{{ status.text }}</p>
          <div class="path-stack">
            <span>缓存 {{ paths.cache }}</span>
            <span>阅读库 {{ paths.library }}</span>
            <span>Qwen {{ paths.qwen || qwen.configPath }}</span>
          </div>
        </section>
      </aside>

      <section class="work-area">
        <SectionSummary
          :section="activeSectionObject"
          :summary="sectionSummary"
          :loading="sectionSummaryLoading"
          :date="selectedDate"
          :range-label="submittedRangeText"
          @summarize="runSectionSummary"
          @copy="copySectionMarkdown"
        />

        <div class="list-head">
          <div>
            <h2>论文列表</h2>
            <p>{{ filteredPapers.length }} / {{ papers.length }} 篇</p>
          </div>
          <div class="message-bar">{{ message }}</div>
        </div>

        <div class="paper-list">
          <div v-if="!filteredPapers.length" class="empty-state">当前筛选下没有论文。</div>
          <section v-for="group in groupedFilteredPapers" :key="group.id" class="paper-group">
            <div class="paper-group-head">
              <div class="paper-group-copy">
                <p class="section-label">分类论文列表</p>
                <h3>{{ group.label }}</h3>
                <p v-if="group.insight?.summary" class="paper-group-summary">
                  <RichText :text="group.insight.summary" />
                </p>
              </div>
              <span>{{ group.papers.length }} 篇</span>
              <details
                v-if="(Array.isArray(group.insight?.highlights) && group.insight.highlights.length) || (Array.isArray(group.insight?.risks) && group.insight.risks.length)"
                class="paper-group-insight"
              >
                <summary>{{ group.insight?.generated ? "Qwen 分类依据" : "相关论文" }}</summary>
                <ul v-if="Array.isArray(group.insight?.highlights) && group.insight.highlights.length">
                  <li v-for="item in group.insight.highlights.slice(0, 3)" :key="item"><RichText :text="item" /></li>
                </ul>
                <p v-if="Array.isArray(group.insight?.risks) && group.insight.risks.length" class="category-risk">
                  <strong>风险：</strong><RichText :text="group.insight.risks.slice(0, 2).join('；')" />
                </p>
              </details>
            </div>
            <PaperCard
              v-for="paper in group.papers"
              :key="paper.id"
              :paper="paper"
              :entry="entryFor(paper.id)"
              :summary="paperSummaries[paper.id]"
              :sections="sections"
              :loading="Boolean(paperLoading[paper.id])"
              @update-library="updateLibrary"
              @summarize="runPaperSummary"
              @copy="copyText"
            />
          </section>
        </div>
      </section>
    </main>

    <div v-if="toast.visible" class="toast">
      <span>{{ toast.text }}</span>
      <button
        v-if="toast.actionLabel"
        class="primary"
        type="button"
        @click="toast.visible = false; toast.action?.()"
      >
        {{ toast.actionLabel }}
      </button>
    </div>
  </div>
</template>
