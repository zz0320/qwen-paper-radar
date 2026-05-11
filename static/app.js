const state = {
  days: 7,
  limit: 18,
  qwen: true,
  loading: false,
};

const els = {
  qwenStatus: document.querySelector("#qwenStatus"),
  refreshButton: document.querySelector("#refreshButton"),
  qwenToggle: document.querySelector("#qwenToggle"),
  limitInput: document.querySelector("#limitInput"),
  dailyBrief: document.querySelector("#dailyBrief"),
  themeList: document.querySelector("#themeList"),
  sourceValue: document.querySelector("#sourceValue"),
  timeValue: document.querySelector("#timeValue"),
  countValue: document.querySelector("#countValue"),
  modeValue: document.querySelector("#modeValue"),
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

function renderPapers(papers) {
  els.paperList.replaceChildren();
  if (!papers.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "当前时间范围没有匹配到论文。可以切换到 7 天，或稍后刷新。";
    els.paperList.append(empty);
    return;
  }

  for (const paper of papers) {
    const node = els.template.content.firstElementChild.cloneNode(true);
    const priority = paper.read_priority || "medium";
    node.querySelector(".priority").className = `priority priority-${priority}`;
    node.querySelector(".priority").textContent = priorityLabel(priority);
    node.querySelector(".category").textContent = paper.primary_category || "arXiv";
    node.querySelector(".date").textContent = formatDate(paper.published);
    node.querySelector(".title").textContent = paper.title;
    node.querySelector(".authors").textContent = (paper.authors || []).slice(0, 8).join(", ");
    node.querySelector(".one-line").textContent = paper.one_line || paper.abstract || "";
    node.querySelector(".why").textContent = paper.why_it_matters || "待 Qwen 梳理。";
    node.querySelector(".limits").textContent = paper.limitations || "待阅读原文确认。";
    renderMethods(node.querySelector(".method-list"), paper.methods || paper.keyword_matches || []);
    node.querySelector(".abs-link").href = paper.arxiv_url;
    node.querySelector(".pdf-link").href = paper.pdf_url;
    els.paperList.append(node);
  }
}

function renderResponse(data) {
  els.dailyBrief.textContent = data.daily_brief || "没有生成总览。";
  renderThemes(data.themes || []);
  els.sourceValue.textContent = data.source || "arXiv";
  els.timeValue.textContent = formatDate(data.generated_at);
  els.countValue.textContent = String((data.papers || []).length);

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

  renderPapers(data.papers || []);
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
    els.themeList.replaceChildren();
    els.paperList.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "请检查网络、arXiv 访问或服务日志。";
    els.paperList.append(empty);
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

els.refreshButton.addEventListener("click", () => loadPapers({ refresh: true }));

loadHealth();
loadPapers();
