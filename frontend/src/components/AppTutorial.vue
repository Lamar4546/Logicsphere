<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['close', 'navigate'])
const step = ref(0)
const steps = [
  { title: 'Welcome to LogiSphere AI', text: 'This control tower helps your team monitor logistics work while agents handle safe routine operations in the background.', target: 'Control Tower' },
  { title: 'Monitor shipments', text: 'Open Shipments to add a shipment, evaluate a delay, inspect the agent timeline, and select Track to view its route, ETA, and carrier event.', target: 'Shipments' },
  { title: 'Run daily operations', text: 'Open Operations for agent-assisted order dispatch, inventory checks, automated delivery tasks, customer alerts, analytics, and returns.', target: 'Operations' },
  { title: 'Know when you are needed', text: 'The agents complete ordinary, non-financial work automatically. Critical risks and any cost, carrier booking, purchase, refund, or commercial commitment wait in Exceptions.', target: 'Exceptions' },
]
const current = computed(() => steps[step.value])
watch(() => props.open, (isOpen) => { if (isOpen) step.value = 0 })
function next() { if (step.value === steps.length - 1) { finish(); return }; step.value += 1 }
function finish() { localStorage.setItem('ls_tutorial_complete', 'true'); emit('close') }
function goToTarget() { emit('navigate', current.value.target) }
</script>

<template>
  <Teleport to="body"><div v-if="open" class="tutorial-backdrop" role="dialog" aria-modal="true" aria-labelledby="tutorial-title"><section class="tutorial-card"><button class="close" aria-label="Close tutorial" @click="emit('close')">×</button><span class="step-count">GETTING STARTED · {{ step + 1 }} / {{ steps.length }}</span><div class="tutorial-icon">{{ step === 0 ? '✦' : step === 1 ? '⌁' : step === 2 ? '◈' : '✓' }}</div><h2 id="tutorial-title">{{ current.title }}</h2><p>{{ current.text }}</p><button v-if="step > 0" class="link" @click="goToTarget">Show me {{ current.target }}</button><div class="progress"><span v-for="(_, index) in steps" :key="index" :class="{ active: index <= step }"></span></div><footer><button class="ghost" @click="finish">Skip tutorial</button><button class="primary" @click="next">{{ step === steps.length - 1 ? 'Finish' : 'Next' }}</button></footer></section></div></Teleport>
</template>

<style scoped>
.tutorial-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:1.25rem;background:rgba(15,28,50,.48);backdrop-filter:blur(4px)}.tutorial-card{position:relative;width:min(100%,470px);padding:2rem;border:1px solid #d7e5f5;border-radius:20px;background:#fff;box-shadow:0 24px 80px rgba(28,61,101,.22)}.close{position:absolute;top:1rem;right:1rem;border:0;background:transparent;font-size:1.5rem;color:#5e7189;padding:.1rem .45rem}.step-count{display:block;color:#55718f;font:.68rem var(--font-mono);letter-spacing:.1em}.tutorial-icon{display:grid;place-items:center;width:3.2rem;height:3.2rem;margin:1.25rem 0 .8rem;border-radius:12px;background:#e7f2ff;color:#1767b4;font-size:1.5rem}.tutorial-card h2{color:#152940;font-size:1.45rem}.tutorial-card p{color:#597087;line-height:1.65}.link{border:0;padding:0;background:none;color:#146cc3;font-weight:600}.progress{display:flex;gap:.4rem;margin:1.5rem 0}.progress span{height:4px;flex:1;border-radius:4px;background:#e5edf6}.progress .active{background:#2a80d5}.tutorial-card footer{display:flex;justify-content:space-between;gap:.75rem}
</style>
