<script setup>
const props = defineProps({
  settings: { type: Object, required: true },
});

const emit = defineEmits(["save"]);

function addKeyword(event) {
  const form = event.currentTarget;
  const input = form.elements.keyword;
  const next = input.value.trim();
  if (!next) return;
  input.value = "";
  emit("save", { keywords: [...props.settings.keywords, next] });
}

function removeKeyword(keyword) {
  emit("save", {
    keywords: props.settings.keywords.filter((item) => item !== keyword),
  });
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>检索关键词</h2>
      <span class="chip">keyword set</span>
    </div>
    <div class="keyword-list">
      <span v-for="keyword in settings.keywords" :key="keyword" class="keyword">
        <span>{{ keyword }}</span>
        <button type="button" title="删除关键词" @click="removeKeyword(keyword)">×</button>
      </span>
    </div>
    <form class="keyword-form" @submit.prevent="addKeyword">
      <input name="keyword" type="text" placeholder="添加关键词" />
      <button type="submit">添加</button>
    </form>
    <label class="field">
      <span>最多抓取</span>
      <input
        type="number"
        min="1"
        max="250"
        step="1"
        :value="settings.maxResults"
        @change="emit('save', { maxResults: Number($event.target.value || 100) })"
      />
    </label>
  </section>
</template>
