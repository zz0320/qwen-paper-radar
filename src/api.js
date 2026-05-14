export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

export function todayLocal() {
  const now = new Date();
  const tzOffset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - tzOffset).toISOString().slice(0, 10);
}

export function markdownForPaper(paper, entry, summary) {
  const lines = [
    `## ${paper.title}`,
    "",
    `- arXiv: ${paper.absUrl}`,
    paper.pdfUrl ? `- PDF: ${paper.pdfUrl}` : "",
    `- ID: ${paper.id}`,
    `- 类别: ${(paper.categories || []).join(", ")}`,
    `- 作者: ${(paper.authors || []).join(", ")}`,
    `- 阅读状态: ${entry.status || "unread"}`,
    entry.category ? `- 本地分类: ${entry.category}` : "",
    "",
    `摘要：${paper.abstract}`,
  ].filter(Boolean);

  if (summary?.abstract_zh) {
    lines.push("", "### 摘要翻译", summary.abstract_zh);
  }

  if (summary?.markdown) {
    lines.push("", "### Qwen 摘要", summary.markdown);
  } else if (summary) {
    lines.push("", "### Qwen 摘要");
    if (summary.one_liner) lines.push(`- 一句话：${summary.one_liner}`);
    if (summary.value) lines.push(`- 价值：${summary.value}`);
    if (summary.limitation) lines.push(`- 局限：${summary.limitation}`);
  }
  if (entry.notes) lines.push("", "### 笔记", entry.notes);
  return lines.join("\n");
}
