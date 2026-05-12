const DEFAULT_CATEGORIES = [
  "未分类",
  "VLA/世界模型",
  "操作/抓取",
  "运动控制",
  "导航/SLAM",
  "仿真/数据",
  "群体/系统",
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
  limit: 18,
  qwen: true,
  loading: false,
  papers: [],
  filtered: [],
  userCategories: DEFAULT_CATEGORIES,
  view: "all",
  category: "all",
  sort: "priority",
  search: "",
};

const noteTimers = new Map();

const els = {
  qwenStatus: document.querySelector("#qwenStatus"),
  refreshButton: document.querySelector("#refreshButton"),
  qwenToggle: document.querySelector("#qwenToggle"),
  limitInput: document.querySelector("#limitInput"),
  searchInput: document.querySelector("#searchInput"),
  categoryFilter: document.querySelector("#categoryFilter"),
  sortSelect: document.querySelector("#sortSelect"),
  clearFiltersButton: document.querySelector("#clearFiltersButton"),
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

function searchableText(paper) {
  return [
    paper.title,
    (paper.authors || []).join(" "),
    paper.one_line,
    paper.why_it_matters,
    paper.limitations,
    (paper.methods || []).join(" "),
    (paper.keyword_matches || []).join(" "),
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
  if (state.view === "high") return paper.read_priority === "high";
  if (state.view === "unread") return paper.status === "unread";
  if (state.view === "reading") return paper.status === "reading";
  if (state.view === "done") return paper.status === "done";
  if (state.view === "notes") return Boolean((paper.notes || "").trim());
  return true;
}

function comparePapers(a, b) {
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

function compareByPriority(a, b) {
  return (
    (PRIORITY_WEIGHT[b.read_priority] || 0) - (PRIORITY_WEIGHT[a.read_priority] || 0) ||
    Number(b.favorite) - Number(a.favorite) ||
    (b.score || 0) - (a.score || 0) ||
    new Date(b.published || 0) - new Date(a.published || 0)
  );
}

function applyFilters() {
  const query = state.search.trim().toLowerCase();
  state.filtered = state.papers
    .filter((paper) => matchesView(paper))
    .filter((paper) => state.category === "all" || paper.user_category === state.category)
    .filter((paper) => !query || searchableText(paper).includes(query))
    .sort(comparePapers);
  renderStats();
  renderPapers(state.filtered);
}

function renderStats() {
  const total = state.papers.length;
  const favorites = state.papers.filter((paper) => paper.favorite).length;
  const high = state.papers.filter((paper) => paper.read_priority === "high").length;
  const tracked = state.papers.filter((paper) => paper.favorite || paper.status !== "unread" || paper.user_category !== "未分类" || paper.notes).length;
  els.countValue.textContent = String(total);
  els.visibleValue.textContent = String(state.filtered.length);
  els.favoriteValue.textContent = String(favorites);
  els.highValue.textContent = String(high);
  els.libraryValue.textContent = tracked ? `${tracked} 条状态` : "未建立";
  els.resultHint.textContent = `${state.filtered.length} / ${total} 篇`;
}

function emptyText() {
  if (!state.papers.length) {
    return "当前时间范围没有匹配到论文。可以切换到 7 天，或稍后刷新。";
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

    const priority = paper.read_priority || "medium";
    const priorityEl = node.querySelector(".priority");
    priorityEl.className = `priority priority-${priority}`;
    priorityEl.textContent = priorityLabel(priority);
    node.querySelector(".category").textContent = paper.primary_category || "arXiv";
    node.querySelector(".user-category-chip").textContent = paper.user_category || "未分类";
    node.querySelector(".date").textContent = formatDate(paper.published);
    node.querySelector(".title").textContent = paper.title;
    node.querySelector(".authors").textContent = (paper.authors || []).slice(0, 8).join(", ");
    node.querySelector(".one-line").textContent = paper.one_line || paper.abstract || "";
    node.querySelector(".why").textContent = paper.why_it_matters || "待 Qwen 梳理。";
    node.querySelector(".limits").textContent = paper.limitations || "待阅读原文确认。";
    renderMethods(node.querySelector(".method-list"), paper.methods || paper.keyword_matches || []);

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

function renderResponse(data) {
  state.papers = (data.papers || []).map((paper) => ({
    favorite: false,
    user_category: "未分类",
    status: "unread",
    notes: "",
    ...paper,
  }));

  els.dailyBrief.textContent = data.daily_brief || "没有生成总览。";
  renderThemes(data.themes || []);
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
  if (state.loading) return;
  setLoading(true);
  const params = new URLSearchParams({
    days: String(state.days),
    limit: String(state.limit),
    qwen: state.qwen ? "1" : "0",
    refresh: refresh ? "1" : "0",
  });

  try {
    const response = await fetch(`/api/papers?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "论文接口请求失败");
    }
    renderResponse(data);
  } catch (error) {
    setStatus("status-error", "抓取失败");
    els.dailyBrief.textContent = error.message;
    state.papers = [];
    state.filtered = [];
    renderThemes([]);
    renderStats();
    renderPapers([]);
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

els.limitInput.addEventListener("change", () => {
  const next = Number(els.limitInput.value || 18);
  state.limit = Math.max(3, Math.min(50, next));
  els.limitInput.value = String(state.limit);
  loadPapers();
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
  state.sort = "priority";
  state.view = "all";
  els.searchInput.value = "";
  els.sortSelect.value = "priority";
  els.categoryFilter.value = "all";
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === "all"));
  applyFilters();
});

els.refreshButton.addEventListener("click", () => loadPapers({ refresh: true }));

loadSettings().then(() => {
  loadHealth();
  loadPapers();
});
