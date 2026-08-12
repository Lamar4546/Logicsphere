<script setup>
import { ref } from 'vue'

const props = defineProps({ recommendation: { type: Object, required: true } })
const emit = defineEmits(['approve', 'reject'])
const busy = ref(false)

async function approve() {
  busy.value = true
  await emit('approve', props.recommendation.id)
  busy.value = false
}
async function reject() {
  busy.value = true
  await emit('reject', props.recommendation.id)
  busy.value = false
}
</script>

<template>
  <div class="panel card">
    <div class="head">
      <span class="badge mono">AI Recommendation</span>
      <span class="confidence mono dim" v-if="recommendation.confidence">
        {{ Math.round(recommendation.confidence * 100) }}% confidence
      </span>
    </div>
    <p class="summary">{{ recommendation.summary }}</p>

    <div class="split">
      <div>
        <span class="mono dim label">Facts</span>
        <ul>
          <li v-for="(f, i) in recommendation.facts" :key="i">{{ f }}</li>
        </ul>
      </div>
      <div>
        <span class="mono dim label">Prediction</span>
        <ul>
          <li v-for="(p, i) in recommendation.predictions" :key="i">{{ p }}</li>
        </ul>
      </div>
    </div>

    <div class="action-box">
      <span class="mono dim label">Recommended action</span>
      <p class="action">{{ recommendation.recommended_action }}</p>
    </div>

    <div class="buttons">
      <button class="primary" :disabled="busy" @click="approve">Approve</button>
      <button class="ghost" :disabled="busy" @click="reject">Reject</button>
    </div>
  </div>
</template>

<style scoped>
.card {
  padding: 1rem;
  margin-bottom: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.badge {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--signal);
  border: 1px solid var(--signal);
  border-radius: 999px;
  padding: 0.15rem 0.55rem;
}
.confidence { font-size: 0.72rem; }
.summary { font-size: 0.9rem; margin: 0; line-height: 1.4; }
.split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  font-size: 0.78rem;
}
.label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  display: block;
  margin-bottom: 0.25rem;
}
ul { margin: 0; padding-left: 1.1rem; }
li { margin-bottom: 0.15rem; }
.action-box {
  background: var(--panel-2);
  border-radius: 6px;
  padding: 0.6rem 0.75rem;
}
.action { margin: 0.2rem 0 0; font-size: 0.85rem; }
.buttons { display: flex; gap: 0.6rem; }
</style>
