<script setup>
defineProps({ process: { type: Object, default: null }, shipment: { type: Object, default: null }, notifications: { type: Array, default: () => [] } })

const stages = [
  ['Tracking signal', 'Transportation Agent'],
  ['Risk assessment', 'Risk Agent + MiniMax reasoning'],
  ['Policy decision', 'Central AI Logistics Manager'],
  ['Execution', 'Autonomous completion or human exception'],
]
</script>

<template>
  <section v-if="process || notifications.length" class="panel process">
    <div class="heading">
      <div>
        <span class="mono dim">AGENT WORKFLOW</span>
        <h2>{{ process?.referenceNumber || shipment?.reference_number }}</h2>
      </div>
      <span v-if="process" class="state" :class="process.status">{{ process.label }}</span>
    </div>
    <div v-if="process" class="stages">
      <div v-for="([title, agent], index) in stages" :key="title" class="step" :class="{ done: process.completedStage > index, active: process.completedStage === index && process.status === 'running' }">
        <span class="node">{{ process.completedStage > index ? '✓' : index + 1 }}</span>
        <div><strong>{{ title }}</strong><small>{{ agent }}</small></div>
      </div>
    </div>
    <p v-if="process?.detail" class="detail">{{ process.detail }}</p>
    <div v-if="notifications.length" class="notifications"><span class="mono dim">MESSAGE DELIVERY</span><p v-for="item in notifications" :key="item.id"><b :class="item.status">{{ item.status }}</b> {{ item.channel }} · {{ item.recipient || 'recipient missing' }} <small v-if="item.error">{{ item.error }}</small></p></div>
  </section>
</template>

<style scoped>
.process { padding: 1rem; margin: 1rem 0; }
.heading { display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; }
h2 { font-size:1rem; margin-top:.2rem; }.heading .mono { font-size:.65rem; letter-spacing:.08em; }
.state { font: .68rem var(--font-mono); text-transform:uppercase; border-radius:999px; padding:.25rem .5rem; border:1px solid var(--line); }.state.completed { color:var(--risk-low); }.state.waiting { color:var(--signal); }.state.failed { color:var(--risk-critical); }
.stages { display:grid; grid-template-columns:repeat(4, 1fr); gap:.4rem; margin-top:1rem; }.step { display:flex; gap:.45rem; align-items:center; color:var(--text-dim); font-size:.75rem; }.node { width:1.35rem; height:1.35rem; display:grid; place-items:center; border:1px solid var(--line); border-radius:50%; font: .68rem var(--font-mono); }.step small { display:block; font-size:.64rem; margin-top:.15rem; }.step.done { color:var(--text); }.step.done .node { background:var(--risk-low); border-color:var(--risk-low); color:#071109; }.step.active .node { border-color:var(--signal); color:var(--signal); box-shadow:0 0 0 3px rgba(242,169,59,.15); }
.detail { margin:.9rem 0 0; color:var(--text-dim); font-size:.82rem; } @media(max-width:700px){.stages{grid-template-columns:1fr 1fr;}}
.notifications{margin-top:1rem;padding-top:.75rem;border-top:1px solid var(--line)}.notifications>span{font-size:.65rem;letter-spacing:.07em}.notifications p{margin:.35rem 0 0;font-size:.75rem;color:var(--text-dim)}.notifications b{text-transform:uppercase;font:.65rem var(--font-mono)}.notifications b.sent{color:var(--risk-low)}.notifications b.failed{color:var(--risk-critical)}.notifications b.pending_approval{color:var(--risk-medium)}.notifications small{display:block;margin-top:.18rem;color:var(--risk-critical)}
</style>
