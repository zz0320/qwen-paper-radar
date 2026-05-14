<script setup>
import { computed } from "vue";
import { renderAcademicText } from "../textRender";

defineOptions({ inheritAttrs: false });

const props = defineProps({
  text: { type: [String, Number, Boolean], default: "" },
  tag: { type: String, default: "span" },
});

const html = computed(() => renderAcademicText(props.text));
</script>

<template>
  <component :is="tag" v-bind="$attrs" class="rich-text" v-html="html" />
</template>
