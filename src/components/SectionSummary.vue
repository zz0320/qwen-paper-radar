<script setup>
import { computed } from "vue";
import RichText from "./RichText.vue";

const props = defineProps({
  section: { type: Object, required: true },
  summary: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  date: { type: String, default: "" },
  rangeLabel: { type: String, default: "" },
});

defineEmits(["summarize", "copy"]);

const dateContext = computed(() => {
  return [props.date, props.rangeLabel || props.section.description].filter(Boolean).join(" · ");
});

const summaryBody = computed(() => props.summary?.summary || null);

const keyTakeaways = computed(() => {
  const rows = summaryBody.value?.key_takeaways;
  return Array.isArray(rows) ? rows.filter(Boolean).slice(0, 4) : [];
});

const watchItems = computed(() => {
  const rows = summaryBody.value?.watchlist;
  return Array.isArray(rows) ? rows.filter(Boolean).slice(0, 4) : [];
});
</script>

<template>
  <section class="summary-panel">
    <div class="summary-head">
      <div>
        <p class="section-label">选定日期论文总结</p>
        <h2>{{ section.label }}</h2>
        <p>{{ dateContext }}</p>
      </div>
      <div class="summary-actions">
        <button type="button" :disabled="loading" @click="$emit('summarize')">
          {{ loading ? "进行中" : "生成选日 Qwen 总结" }}
        </button>
        <button type="button" @click="$emit('copy')">复制总结 Markdown</button>
      </div>
    </div>

    <div v-if="loading" class="summary-content loading">Qwen 总结进行中...</div>
    <div v-else-if="!summaryBody" class="summary-content empty-state">
      <p>尚未生成选定日期总结。下方论文列表会按专业分类聚合；生成总结后，分类判断会直接并入各分组。</p>
    </div>
    <div v-else class="summary-content summary-compact">
      <section class="summary-hero">
        <p class="section-label">Qwen 选日结论</p>
        <h3><RichText :text="summaryBody.headline || '本页总结'" /></h3>
      </section>

      <details v-if="keyTakeaways.length || watchItems.length" class="summary-more">
        <summary>展开核心判断与后续关注</summary>
        <section v-if="keyTakeaways.length" class="summary-decision">
          <h3>核心判断</h3>
          <ul>
            <li v-for="item in keyTakeaways" :key="item"><RichText :text="item" /></li>
          </ul>
        </section>

        <section v-if="watchItems.length" class="summary-watch">
          <h3>后续关注</h3>
          <div>
            <span v-for="item in watchItems" :key="item"><RichText :text="item" /></span>
          </div>
        </section>
      </details>
    </div>
  </section>
</template>
