<script setup>
import { ref } from 'vue'

const props = defineProps({ communication: { type: Object, required: true } })
const emit = defineEmits(['send'])
const busy = ref(false)

async function send() {
  busy.value = true
  await emit('send', {
    communicationId: props.communication.id,
    recommendationId: props.communication.recommendation_id,
  })
  busy.value = false
}
</script>

<template>
  <div class="panel card">
    <div class="head">
      <span class="badge mono">Draft · {{ communication.channel }}</span>
    </div>
    <p class="subject">{{ communication.subject }}</p>
    <pre class="body">{{ communication.body }}</pre>
    <div class="buttons">
      <button class="primary" :disabled="busy" @click="send">Approve &amp; Send</button>
    </div>
  </div>
</template>

<style scoped>
.card {
  padding: 1rem;
  margin-bottom: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.head { display: flex; }
.badge {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.15rem 0.55rem;
}
.subject { font-weight: 600; font-size: 0.88rem; margin: 0; }
.body {
  white-space: pre-wrap;
  font-family: var(--font-body);
  font-size: 0.82rem;
  background: var(--panel-2);
  border-radius: 6px;
  padding: 0.65rem 0.75rem;
  margin: 0;
  color: var(--text-dim);
}
.buttons { display: flex; }
</style>
