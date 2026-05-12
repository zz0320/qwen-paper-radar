const DEFAULT_CATEGORIES = [
  "未分类",
  "本体/硬件",
  "预训练",
  "后训练",
  "RL/DAgger",
  "具身数据",
  "具身推理",
  "移动操作",
  "灵巧操作",
  "灵巧手",
  "仿真/Sim2Real",
  "评测/Benchmark",
  "待复现",
];

const STATUS_LABELS = {
  unread: "未读",
  reading: "在读",
  done: "已读",
  skip: "跳过",
};

const PRIORITY_WEIGHT = {
  high: 3,
  medium: 2,
  low: 1,
};

const state = {
  days: 7,
  pageSize: 12,
  nextOffset: 0,
  totalAvailable: 0,
  hasMore: true,
  qwen: true,
  loading: false,
  papers: [],
  filtered: [],
  userCategories: DEFAULT_CATEGORIES,
  dailyBrief: "",
  themes: [],
  generatedAt: "",
  digestMarkdown: "",
  view: "all",
  category: "all",
  sort: "industry",
  search: "",
};

const noteTimers = new Map();

const els = {
  qwenStatus: document.querySelector("#qwenStatus"),
  refreshButton: document.querySelector("#refreshButton"),
  qwenToggle: document.querySelector("#qwenToggle"),
  searchInput: document.querySelector("#searchInput"),
  categoryFilter: document.querySelector("#categoryFilter"),
  sortSelect: document.querySelector("#sortSelect"),
  clearFiltersButton: document.querySelector("#clearFiltersButton"),
  copyDigestButton: document.querySelector("#copyDigestButton"),
  copyDigestStatus: document.querySelector("#copyDigestStatus"),
  briefScope: document.querySelector("#briefScope"),
  digestTitle: document.querySelector("#digestTitle"),
  digestDate: document.querySelector("#digestDate"),
  digestLead: document.querySelector("#digestLead"),
  digestMustRead: document.querySelector("#digestMustRead"),
  digestSignals: document.querySelector("#digestSignals"),
  digestQueue: document.querySelector("#digestQueue"),
  dailyBrief: document.querySelector("#dailyBrief"),
  themeList: document.querySelector("#themeList"),
  sourceValue: document.querySelector("#sourceValue"),
  timeValue: document.querySelector("#timeValue"),
  countValue: document.querySelector("#countValue"),
  visibleValue: document.querySelector("#visibleValue"),
  favoriteValue: document.querySelector("#favoriteValue"),
  highValue: document.querySelector("#highValue"),
  libraryValue: document.querySelector("#libraryValue"),
  modeValue: document.querySelector("#modeValue"),
  resultHint: document.querySelector("#resultHint"),
  paperList: document.querySelector("#paperList"),
  feedSentinel: document.querySelector("#feedSentinel"),
  feedStatus: document.querySelector("#feedStatus"),
  template: document.querySelector("#paperTemplate"),
};

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatReportDate(value) {
  const date = value ? new Date(value) : new Date();
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  }).format(date);
}

function rangeLabel(days = state.days) {
  if (Number(days) === 1) return "今日";
  return `近 ${days} 天`;
}

function rangeSummaryLabel(days = state.days) {
  return `${rangeLabel(days)}总览`;
}

function rangeDigestTitle(days = state.days) {
  return `${rangeLabel(days)}阅读简报`;
}

function priorityLabel(value) {
  if (value === "high") return "高优先级";
  if (value === "low") return "低优先级";
  return "中优先级";
}

function setStatus(kind, text) {
  els.qwenStatus.className = `status ${kind}`;
  els.qwenStatus.textContent = text;
}

function setLoading(loading) {
  state.loading = loading;
  els.refreshButton.disabled = loading;
  els.refreshButton.querySelector("span").textContent = loading ? "…" : "↻";
  renderFeedStatus();
}

function renderCategoryOptions(select, selected, includeAll = false) {
  select.replaceChildren();
  if (includeAll) {
    const option = document.createElement("option");
    option.value = "all";
    option.textContent = "全部分类";
    select.append(option);
  }
  for (const category of state.userCategories) {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    option.selected = category === selected;
    select.append(option);
  }
  if (includeAll && selected === "all") {
    select.value = "all";
  }
}

function renderThemes(themes) {
  els.themeList.replaceChildren();
  for (const theme of themes || []) {
    const item = document.createElement("span");
    item.className = "theme";
    item.textContent = theme;
    els.themeList.append(item);
  }
}

function renderMethods(container, methods) {
  container.replaceChildren();
  const values = (methods || []).filter(Boolean).slice(0, 5);
  for (const method of values) {
    const item = document.createElement("span");
    item.className = "method";
    item.textContent = method;
    container.append(item);
  }
}

function renderSignals(container, signals) {
  container.replaceChildren();
  const values = (signals || []).filter(Boolean).slice(0, 6);
  for (const signal of values) {
    const item = document.createElement("span");
    item.className = "signal";
    item.textContent = signal;
    container.append(item);
  }
}

function searchableText(paper) {
  return [
    paper.title,
    (paper.authors || []).join(" "),
    paper.one_line,
    paper.why_it_matters,
    paper.limitations,
    (paper.methods || []).join(" "),
    (paper.keyword_matches || []).join(" "),
    (paper.industry_signals || []).join(" "),
    paper.industry_label,
    paper.industry_level,
    paper.abstract,
    paper.user_category,
    paper.notes,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function matchesView(paper) {
  if (state.view === "favorites") return paper.favorite;
  if (state.view === "core") return paper.industry_level === "core" || paper.industry_level === "watch";
  if (state.view === "high") return paper.read_priority === "high";
  if (state.view === "unread") return paper.status === "unread";
  if (state.view === "reading") return paper.status === "reading";
  if (state.view === "done") return paper.status === "done";
  if (state.view === "notes") return Boolean((paper.notes || "").trim());
  return true;
}

function comparePapers(a, b) {
  if (state.sort === "industry") {
    return compareByIndustry(a, b);
  }
  if (state.sort === "date") {
    return new Date(b.published || 0) - new Date(a.published || 0);
  }
  if (state.sort === "favorite") {
    return Number(b.favorite) - Number(a.favorite) || compareByPriority(a, b);
  }
  if (state.sort === "category") {
    return String(a.user_category || "").localeCompare(String(b.user_category || ""), "zh-CN") || compareByPriority(a, b);
  }
  return compareByPriority(a, b);
}

function compareByIndustry(a, b) {
  return (
    (b.industry_score || 0) - (a.industry_score || 0) ||
    compareByPriority(a, b)
  );
}

function compareByPriority(a, b) {
  return (
    (PRIORITY_WEIGHT[b.read_priority] || 0) - (PRIORITY_WEIGHT[a.read_priority] || 0) ||
    (b.industry_score || 0) - (a.industry_score || 0) ||
    Number(b.favorite) - Number(a.favorite) ||
    (b.score || 0) - (a.score || 0) ||
    new Date(b.published || 0) - new Date(a.published || 0)
  );
}

function appendListItem(list, text) {
  const item = document.createElement("li");
  item.textContent = text;
  list.append(item);
}

function topPapers(count = 3) {
  return [...state.papers]
    .sort(compareByIndustry)
    .slice(0, count);
}

function countedSignals(source) {
  const counts = new Map();
  for (const value of source) {
    const key = String(value).trim();
    if (!key) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([name, count]) => `${name} (${count})`);
}

function industrySignals() {
  return countedSignals(state.papers.flatMap((paper) => paper.industry_signals || []));
}

function methodSignals() {
  const source = [];
  for (const paper of state.papers) {
    for (const method of paper.methods || paper.keyword_matches || []) {
      source.push(method);
    }
  }
  return countedSignals(source);
}

function digestSignals() {
  const industry = industrySignals();
  if (industry.length) return industry;
  const themes = (state.themes || []).filter(Boolean).slice(0, 4);
  if (themes.length) return themes;
  return methodSignals();
}

function digestQueue() {
  const scope = rangeLabel();
  const highCount = state.papers.filter((paper) => paper.read_priority === "high").length;
  const coreCount = state.papers.filter((paper) => paper.industry_level === "core" || paper.industry_level === "watch").length;
  const favorites = state.papers.filter((paper) => paper.favorite).length;
  const unread = state.papers.filter((paper) => paper.status === "unread").length;
  const reading = state.papers.filter((paper) => paper.status === "reading").length;
  const notes = state.papers.filter((paper) => (paper.notes || "").trim()).length;
  return [
    `${scope}先读 ${coreCount || highCount} 篇核心/重点论文，重点确认真机、数据、开源和可复现性`,
    favorites ? `复查 ${favorites} 篇已收藏论文，补充复现或项目关联笔记` : `从必读列表中挑 1-2 篇加入收藏或待复现`,
    reading ? `${reading} 篇在读论文需要收口结论` : `${unread} 篇仍未读，可按分类分批处理`,
    notes ? `${notes} 篇已有笔记，适合沉淀到周报或项目 backlog` : `读完后在卡片里补一条笔记，方便后续检索`,
  ];
}

function buildDigestMarkdown(mustRead, signals, queue) {
  const date = formatReportDate(state.generatedAt);
  const lines = [
    `# 具身智读速览｜${rangeLabel()}｜${date}`,
    "",
    `> ${state.dailyBrief || `暂无${rangeLabel()}总览。`}`,
    "",
    "## 必读论文",
  ];
  if (mustRead.length) {
    mustRead.forEach((paper, index) => {
      lines.push(`${index + 1}. [${paper.title}](${paper.arxiv_url})`);
      const signalText = (paper.industry_signals || []).slice(0, 4).join("、") || "待补充产业信号";
      lines.push(`   - ${paper.one_line || paper.why_it_matters || "待阅读原文确认。"}`);
      lines.push(`   - 产业信号：${paper.industry_label || "快速扫读"}｜${signalText}`);
    });
  } else {
    lines.push("- 暂无匹配论文。");
  }
  lines.push("", "## 方向信号");
  for (const signal of signals) {
    lines.push(`- ${signal}`);
  }
  lines.push("", "## 阅读队列");
  for (const item of queue) {
    lines.push(`- ${item}`);
  }
  return lines.join("\n");
}

function renderDigest() {
  const mustRead = topPapers(3);
  const signals = digestSignals();
  const queue = digestQueue();

  els.briefScope.textContent = rangeSummaryLabel();
  els.digestTitle.textContent = rangeDigestTitle();
  els.digestDate.textContent = `${formatReportDate(state.generatedAt)} · ${rangeLabel()}`;
  els.digestLead.textContent = state.dailyBrief || `暂无${rangeLabel()}总览。`;
  els.digestMustRead.replaceChildren();
  els.digestSignals.replaceChildren();
  els.digestQueue.replaceChildren();

  if (!state.papers.length) {
    appendListItem(els.digestMustRead, "暂无匹配论文");
    appendListItem(els.digestSignals, "等待新的机器人/具身智能论文");
    appendListItem(els.digestQueue, "稍后刷新或扩大时间范围");
    state.digestMarkdown = buildDigestMarkdown([], ["等待新的机器人/具身智能论文"], ["稍后刷新或扩大时间范围"]);
    return;
  }

  for (const paper of mustRead) {
    appendListItem(els.digestMustRead, `${paper.title}｜${paper.one_line || paper.why_it_matters || "待阅读原文确认"}`);
  }
  for (const signal of signals) {
    appendListItem(els.digestSignals, signal);
  }
  for (const item of queue) {
    appendListItem(els.digestQueue, item);
  }
  state.digestMarkdown = buildDigestMarkdown(mustRead, signals, queue);
}

function applyFilters() {
  const query = state.search.trim().toLowerCase();
  state.filtered = state.papers
    .filter((paper) => matchesView(paper))
    .filter((paper) => state.category === "all" || paper.user_category === state.category)
    .filter((paper) => !query || searchableText(paper).includes(query))
    .sort(comparePapers);
  renderStats();
  renderDigest();
  renderPapers(state.filtered);
}

function renderStats() {
  const total = state.papers.length;
  const favorites = state.papers.filter((paper) => paper.favorite).length;
  const high = state.papers.filter((paper) => paper.industry_level === "core" || paper.industry_level === "watch").length;
  const tracked = state.papers.filter((paper) => paper.favorite || paper.status !== "unread" || paper.user_category !== "未分类" || paper.notes).length;
  els.countValue.textContent = String(total);
  els.visibleValue.textContent = String(state.filtered.length);
  els.favoriteValue.textContent = String(favorites);
  els.highValue.textContent = String(high);
  els.libraryValue.textContent = tracked ? `${tracked} 条状态` : "未建立";
  const available = state.totalAvailable || total;
  els.resultHint.textContent = state.hasMore
    ? `已加载 ${total} / ${available} 篇`
    : `${state.filtered.length} / ${total} 篇`;
  renderFeedStatus();
}

function emptyText() {
  if (!state.papers.length) {
    return `当前${rangeLabel()}范围没有匹配到论文。可以切换到更长时间范围，或稍后刷新。`;
  }
  return "没有论文符合当前筛选。可以清空搜索、切换分类或查看全部。";
}

function renderPapers(papers) {
  els.paperList.replaceChildren();
  if (!papers.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = emptyText();
    els.paperList.append(empty);
    return;
  }

  for (const paper of papers) {
    const node = els.template.content.firstElementChild.cloneNode(true);
    node.dataset.id = paper.id;
    node.classList.toggle("is-favorite", Boolean(paper.favorite));
    node.classList.toggle("is-done", paper.status === "done");
    node.classList.add(`level-${paper.industry_level || "archive"}`);

    const priority = paper.read_priority || "medium";
    const priorityEl = node.querySelector(".priority");
    priorityEl.className = `priority priority-${priority}`;
    priorityEl.textContent = priorityLabel(priority);
    const industryEl = node.querySelector(".industry-level");
    industryEl.className = `industry-level industry-${paper.industry_level || "scan"}`;
    industryEl.textContent = paper.industry_label || "快速扫读";
    node.querySelector(".category").textContent = paper.primary_category || "arXiv";
    node.querySelector(".user-category-chip").textContent = paper.user_category || "未分类";
    node.querySelector(".date").textContent = formatDate(paper.published);
    node.querySelector(".industry-score").textContent = String(paper.industry_score || 0);
    node.querySelector(".title").textContent = paper.title;
    node.querySelector(".authors").textContent = (paper.authors || []).slice(0, 8).join(", ");
    node.querySelector(".one-line").textContent = paper.one_line || paper.abstract || "";
    node.querySelector(".why").textContent = paper.why_it_matters || "待 Qwen 梳理。";
    node.querySelector(".limits").textContent = paper.limitations || "待阅读原文确认。";
    renderMethods(node.querySelector(".method-list"), paper.methods || paper.keyword_matches || []);
    renderSignals(node.querySelector(".signal-list"), paper.industry_signals || []);

    const favoriteButton = node.querySelector(".favorite-button");
    favoriteButton.textContent = paper.favorite ? "★" : "☆";
    favoriteButton.setAttribute("aria-pressed", String(Boolean(paper.favorite)));
    favoriteButton.addEventListener("click", () => savePaperState(paper.id, { favorite: !paper.favorite }));

    const categorySelect = node.querySelector(".category-select");
    renderCategoryOptions(categorySelect, paper.user_category || "未分类");
    categorySelect.addEventListener("change", () => savePaperState(paper.id, { user_category: categorySelect.value }));

    node.querySelectorAll("[data-status]").forEach((button) => {
      const status = button.dataset.status;
      button.classList.toggle("active", paper.status === status);
      button.addEventListener("click", () => savePaperState(paper.id, { status }));
    });

    const notes = node.querySelector(".notes");
    const saveStatus = node.querySelector(".save-status");
    notes.value = paper.notes || "";
    notes.addEventListener("input", () => scheduleNoteSave(paper.id, notes.value, saveStatus));

    if (paper.notes) {
      node.querySelector(".note-box").open = true;
    }

    node.querySelector(".abs-link").href = paper.arxiv_url;
    node.querySelector(".pdf-link").href = paper.pdf_url;
    els.paperList.append(node);
  }
}

function renderFeedStatus() {
  if (!els.feedSentinel || !els.feedStatus) return;
  if (state.loading && state.papers.length) {
    els.feedSentinel.classList.remove("is-done", "is-hidden");
    els.feedSentinel.classList.add("is-loading");
    els.feedStatus.textContent = "正在加载下一批论文...";
    return;
  }

  els.feedSentinel.classList.remove("is-loading");
  if (!state.papers.length) {
    els.feedSentinel.classList.add("is-hidden");
    return;
  }

  els.feedSentinel.classList.remove("is-hidden");
  if (state.hasMore) {
    els.feedSentinel.classList.remove("is-done");
    els.feedStatus.textContent = "继续下滑加载更多论文";
  } else {
    els.feedSentinel.classList.add("is-done");
    els.feedStatus.textContent = "当前时间范围已全部加载";
  }
}

function updateLocalPaper(id, changes) {
  const paper = state.papers.find((item) => item.id === id);
  if (!paper) return null;
  Object.assign(paper, changes);
  return paper;
}

async function savePaperState(id, changes, options = { rerender: true }) {
  updateLocalPaper(id, changes);
  if (options.rerender) {
    applyFilters();
  } else {
    renderStats();
  }

  try {
    const response = await fetch("/api/library/paper", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, ...changes }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "保存失败");
    }
    updateLocalPaper(id, data.state);
    if (options.rerender) {
      applyFilters();
    } else {
      renderStats();
    }
    return data.state;
  } catch (error) {
    setStatus("status-error", "本地库保存失败");
    console.error(error);
    throw error;
  }
}

function scheduleNoteSave(id, value, saveStatus) {
  updateLocalPaper(id, { notes: value });
  saveStatus.textContent = "保存中...";
  renderStats();

  if (noteTimers.has(id)) {
    clearTimeout(noteTimers.get(id));
  }
  noteTimers.set(
    id,
    setTimeout(async () => {
      try {
        await savePaperState(id, { notes: value }, { rerender: false });
        saveStatus.textContent = "已保存";
      } catch (error) {
        saveStatus.textContent = "保存失败";
      }
      noteTimers.delete(id);
    }, 650),
  );
}

function normalizePaper(paper) {
  return {
    favorite: false,
    user_category: "未分类",
    status: "unread",
    notes: "",
    industry_signals: [],
    industry_score: 0,
    industry_level: "archive",
    industry_label: "归档备查",
    ...paper,
  };
}

function mergePapers(nextPapers) {
  const seen = new Set(state.papers.map((paper) => paper.id));
  for (const paper of nextPapers) {
    if (seen.has(paper.id)) continue;
    state.papers.push(paper);
    seen.add(paper.id);
  }
}

function mergeThemes(nextThemes) {
  const merged = new Set(state.themes || []);
  for (const theme of nextThemes || []) {
    if (theme) merged.add(theme);
  }
  state.themes = [...merged].slice(0, 8);
}

function renderResponse(data, { append = false } = {}) {
  const nextPapers = (data.papers || []).map(normalizePaper);
  if (append) {
    mergePapers(nextPapers);
  } else {
    state.papers = nextPapers;
  }

  const pagination = data.pagination || {};
  state.nextOffset = pagination.next_offset ?? state.papers.length;
  state.totalAvailable = pagination.total ?? state.papers.length;
  state.hasMore = Boolean(pagination.has_more);

  if (!append || !state.dailyBrief) {
    state.dailyBrief = data.daily_brief || "";
  }
  if (append) {
    mergeThemes(data.themes || []);
  } else {
    state.themes = data.themes || [];
  }
  state.generatedAt = data.generated_at || "";
  els.dailyBrief.textContent = state.dailyBrief || "没有生成总览。";
  renderThemes(state.themes || []);
  els.sourceValue.textContent = data.source || "arXiv";
  els.timeValue.textContent = formatDate(data.generated_at);

  if (data.qwen?.used) {
    const cached = data.qwen.cached ? "缓存" : data.qwen.model;
    setStatus("status-ok", `Qwen 已启用 · ${cached}`);
    els.modeValue.textContent = "Qwen 模式";
  } else if (data.qwen?.enabled) {
    setStatus("status-warn", "Qwen 未返回，已降级");
    els.modeValue.textContent = "规则模式";
  } else {
    setStatus("status-warn", "未配置 API key");
    els.modeValue.textContent = "规则模式";
  }

  if (data.qwen?.error) {
    console.warn("Qwen summary failed:", data.qwen.error);
  }

  applyFilters();
}

async function copyDigest() {
  if (!state.digestMarkdown) return;
  try {
    await navigator.clipboard.writeText(state.digestMarkdown);
    els.copyDigestStatus.textContent = "日报已复制";
  } catch (error) {
    const textarea = document.createElement("textarea");
    textarea.value = state.digestMarkdown;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    els.copyDigestStatus.textContent = "日报已复制";
  }
  setTimeout(() => {
    els.copyDigestStatus.textContent = "";
  }, 1800);
}

async function loadSettings() {
  try {
    const response = await fetch("/api/settings");
    const data = await response.json();
    if (Array.isArray(data.user_categories) && data.user_categories.length) {
      state.userCategories = data.user_categories;
    }
  } catch (error) {
    state.userCategories = DEFAULT_CATEGORIES;
  }
  renderCategoryOptions(els.categoryFilter, state.category, true);
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (data.has_qwen_key) {
      setStatus("status-ok", `Qwen 就绪 · ${data.qwen_model}`);
    } else {
      setStatus("status-warn", "未配置 API key");
    }
  } catch (error) {
    setStatus("status-error", "服务未就绪");
  }
}

async function loadPapers({ refresh = false } = {}) {
  return loadFeedPage({ refresh, append: false });
}

async function loadNextPage() {
  if (!state.hasMore || state.loading) return;
  return loadFeedPage({ append: true });
}

async function loadFeedPage({ refresh = false, append = false } = {}) {
  if (state.loading) return;
  if (!append) {
    state.nextOffset = 0;
    state.totalAvailable = 0;
    state.hasMore = true;
  }
  setLoading(true);
  const params = new URLSearchParams({
    days: String(state.days),
    offset: String(append ? state.nextOffset : 0),
    page_size: String(state.pageSize),
    qwen: state.qwen ? "1" : "0",
    refresh: refresh ? "1" : "0",
  });

  try {
    const response = await fetch(`/api/papers?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "论文接口请求失败");
    }
    renderResponse(data, { append });
  } catch (error) {
    setStatus("status-error", "抓取失败");
    if (!append) {
      els.dailyBrief.textContent = error.message;
      state.papers = [];
      state.filtered = [];
      state.hasMore = false;
      renderThemes([]);
      renderStats();
      renderPapers([]);
    }
  } finally {
    setLoading(false);
  }
}

document.querySelectorAll("[data-days]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-days]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.days = Number(button.dataset.days);
    loadPapers();
  });
});

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.view = button.dataset.view;
    applyFilters();
  });
});

els.qwenToggle.addEventListener("change", () => {
  state.qwen = els.qwenToggle.checked;
  loadPapers();
});

els.searchInput.addEventListener("input", () => {
  state.search = els.searchInput.value;
  applyFilters();
});

els.categoryFilter.addEventListener("change", () => {
  state.category = els.categoryFilter.value;
  applyFilters();
});

els.sortSelect.addEventListener("change", () => {
  state.sort = els.sortSelect.value;
  applyFilters();
});

els.clearFiltersButton.addEventListener("click", () => {
  state.search = "";
  state.category = "all";
  state.view = "all";
  els.searchInput.value = "";
  state.sort = "industry";
  els.sortSelect.value = "industry";
  els.categoryFilter.value = "all";
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === "all"));
  applyFilters();
});

els.refreshButton.addEventListener("click", () => loadPapers({ refresh: true }));
els.copyDigestButton.addEventListener("click", copyDigest);

if ("IntersectionObserver" in window && els.feedSentinel) {
  const feedObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        loadNextPage();
      }
    },
    { rootMargin: "700px 0px 900px" },
  );
  feedObserver.observe(els.feedSentinel);
}

loadSettings().then(() => {
  loadHealth();
  loadPapers();
});
