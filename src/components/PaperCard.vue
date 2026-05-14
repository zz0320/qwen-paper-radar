<script setup>
import { computed, reactive, ref, watch } from "vue";
import { markdownForPaper } from "../api";
import RichText from "./RichText.vue";

const props = defineProps({
  paper: { type: Object, required: true },
  entry: { type: Object, required: true },
  summary: { type: Object, default: null },
  sections: { type: Array, required: true },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(["update-library", "summarize", "copy"]);

const draft = reactive({
  category: props.entry.category || "",
  notes: props.entry.notes || "",
});
const abstractExpanded = ref(false);

watch(
  () => props.entry,
  (entry) => {
    draft.category = entry.category || "";
    draft.notes = entry.notes || "";
  },
);

const authorLine = computed(() => {
  const authors = props.paper.authors || [];
  const head = authors.slice(0, 6).join(", ");
  return authors.length > 6 ? `${head} 等 ${authors.length} 人` : head;
});

const sectionLabelMap = computed(() => {
  return Object.fromEntries(props.sections.map((item) => [item.id, item.label]));
});

const summaryBody = computed(() => props.summary?.summary || null);
const hasAbstractTranslation = computed(() => Boolean(summaryBody.value?.abstract_zh));
const summarizeButtonLabel = computed(() => {
  if (props.loading) return "进行中";
  if (summaryBody.value && !hasAbstractTranslation.value) return "补全摘要翻译";
  return "生成单篇总结";
});
const shouldReadText = computed(() => {
  const value = summaryBody.value?.should_read;
  if (value === true) return "建议阅读";
  if (value === false) return "可略读";
  return value ? String(value) : "";
});
const primaryTags = computed(() => {
  const primarySection = props.paper.primarySection;
  const sectionTags = (props.paper.sections || [])
    .filter((section) => section !== primarySection)
    .map((section) => sectionLabelMap.value[section] || section);
  const primaryLabel = primarySection ? sectionLabelMap.value[primarySection] || primarySection : "";
  return [
    primaryLabel ? `主类 ${primaryLabel}` : "",
    ...sectionTags,
    ...(props.paper.matchedKeywords || []),
  ].filter(Boolean);
});

function copyMarkdown() {
  emit("copy", markdownForPaper(props.paper, props.entry, summaryBody.value));
}
</script>

<template>
  <article class="paper-card">
    <div class="paper-shell">
      <section class="paper-main">
        <div class="paper-top">
          <div class="paper-heading">
            <h3 class="paper-title">
              <a :href="paper.absUrl" target="_blank" rel="noreferrer">
                <RichText :text="paper.title" />
              </a>
            </h3>
            <div class="paper-meta">
              <span>{{ paper.id }}</span>
              <span>{{ (paper.submittedDate || paper.published || "").slice(0, 10) }}</span>
              <span>{{ paper.primaryCategory }}</span>
              <span>相关度 {{ paper.relevanceScore || 0 }}</span>
            </div>
            <div class="paper-authors">{{ authorLine }}</div>
          </div>
        </div>

        <div class="tags paper-tags">
          <span v-for="tag in primaryTags" :key="tag" class="tag">{{ tag }}</span>
        </div>

        <div class="abstract-block" :class="{ expanded: abstractExpanded }">
          <RichText tag="p" class="abstract" :text="paper.abstract" />
          <button class="abstract-toggle" type="button" @click="abstractExpanded = !abstractExpanded">
            {{ abstractExpanded ? "收起摘要" : "展开摘要" }}
          </button>
        </div>
        <div v-if="hasAbstractTranslation" class="abstract-translation">
          <div class="abstract-translation-label">Qwen 摘要翻译</div>
          <RichText tag="p" :text="summaryBody.abstract_zh" />
        </div>

        <div class="paper-links">
          <a :href="paper.absUrl" target="_blank" rel="noreferrer">arXiv</a>
          <a v-if="paper.pdfUrl" :href="paper.pdfUrl" target="_blank" rel="noreferrer">PDF</a>
          <button type="button" @click="copyMarkdown">复制 Markdown</button>
          <button type="button" :disabled="loading" @click="emit('summarize', paper.id)">
            {{ summarizeButtonLabel }}
          </button>
        </div>
      </section>

      <aside class="paper-sidebar">
        <button
          class="favorite-button"
          :class="{ active: entry.favorite }"
          type="button"
          @click="emit('update-library', paper.id, { favorite: !entry.favorite })"
        >
          {{ entry.favorite ? "已收藏" : "收藏" }}
        </button>
        <div class="paper-summary" :class="{ loading, empty: !summaryBody && !loading }">
          <div class="paper-summary-label">单篇论文总结</div>
          <span v-if="loading">Qwen 摘要进行中...</span>
          <span v-else-if="!summaryBody" class="empty-state">尚未生成。</span>
          <template v-else>
            <p v-if="summaryBody.abstract_zh" class="summary-translation-note">中文摘要已生成，见左侧摘要下方。</p>
            <p v-if="summaryBody.one_liner"><strong>一句话：</strong><RichText :text="summaryBody.one_liner" /></p>
            <p v-if="summaryBody.value"><strong>价值：</strong><RichText :text="summaryBody.value" /></p>
            <p v-if="summaryBody.limitation"><strong>局限：</strong><RichText :text="summaryBody.limitation" /></p>
            <p v-if="summaryBody.method"><strong>方法：</strong><RichText :text="summaryBody.method" /></p>
            <p v-if="shouldReadText"><strong>阅读建议：</strong><RichText :text="shouldReadText" /></p>
            <pre v-if="!summaryBody.one_liner && summaryBody.markdown">{{ summaryBody.markdown }}</pre>
          </template>
        </div>

        <div class="paper-controls">
          <label class="field">
            <span>阅读状态</span>
            <select
              :value="entry.status"
              @change="emit('update-library', paper.id, { status: $event.target.value })"
            >
              <option value="unread">未读</option>
              <option value="queued">待读</option>
              <option value="reading">在读</option>
              <option value="done">已读</option>
            </select>
          </label>
          <label class="field">
            <span>分类</span>
            <input v-model="draft.category" type="text" placeholder="必读 / 数据 / 复现" />
          </label>
          <div class="notes-row">
            <label class="field">
              <span>笔记</span>
              <textarea v-model="draft.notes" placeholder="本地笔记"></textarea>
            </label>
            <button
              type="button"
              @click="emit('update-library', paper.id, { category: draft.category, notes: draft.notes })"
            >
              保存
            </button>
          </div>
        </div>
      </aside>
    </div>
  </article>
</template>
