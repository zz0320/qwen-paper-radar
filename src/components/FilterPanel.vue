<script setup>
const model = defineModel({ type: Object, required: true });
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>筛选</h2>
    </div>
    <label class="field">
      <span>排序</span>
      <select v-model="model.sort">
        <option value="date_desc">提交时间新到旧</option>
        <option value="score_desc">相关度高到低</option>
        <option value="title_asc">标题 A-Z</option>
        <option value="favorite_first">收藏优先</option>
      </select>
    </label>
    <label class="check-row">
      <input v-model="model.favoriteOnly" type="checkbox" />
      <span>只看收藏</span>
    </label>
    <label class="field">
      <span>阅读状态</span>
      <select v-model="model.status">
        <option value="">全部</option>
        <option value="unread">未读</option>
        <option value="queued">待读</option>
        <option value="reading">在读</option>
        <option value="done">已读</option>
      </select>
    </label>
  </section>
</template>
