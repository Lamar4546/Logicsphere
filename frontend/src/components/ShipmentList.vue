<script setup>
defineProps({ shipments: { type: Array, required: true }, selectedId: { type: String, default: null }, evaluatingId: { type: String, default: null } })
const emit = defineEmits(['evaluate', 'select'])

function statusClass(status) {
  return { at_risk: 'at_risk', delayed: 'at_risk', delivered: 'ok' }[status] || 'neutral'
}
</script>

<template>
  <div class="list">
    <p v-if="!shipments.length" class="empty">No shipments yet — add one above.</p>
    <div v-for="s in shipments" :key="s.id" class="panel row" :class="[statusClass(s.status), { selected: s.id === selectedId }]">
      <div class="rail" :class="statusClass(s.status)"></div>
      <div class="body">
        <div class="line1">
          <span class="ref mono">{{ s.reference_number }}</span>
          <span class="status mono dim">{{ s.status }}</span>
        </div>
        <div class="line2 dim">{{ s.origin || '—' }} → {{ s.destination || '—' }}</div>
        <div class="line3 dim mono" v-if="s.eta_original || s.eta_current">
          ETA orig {{ s.eta_original ? new Date(s.eta_original).toLocaleString() : '—' }}
          · ETA now {{ s.eta_current ? new Date(s.eta_current).toLocaleString() : '—' }}
        </div>
      </div>
      <div class="buttons"><button class="ghost" @click="emit('select', s)">Track</button><button :disabled="evaluatingId === s.id" @click="emit('evaluate', s)">{{ evaluatingId === s.id ? 'Evaluating…' : 'Evaluate' }}</button></div>
    </div>
  </div>
</template>

<style scoped>
.list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.85rem 1rem 0.85rem 0;
  overflow: hidden;
}
.row.selected { border-color: var(--signal); }
.buttons { display:flex; gap:.45rem; }
.rail {
  width: 4px;
  align-self: stretch;
  border-radius: 2px;
  background: var(--line);
}
.rail.at_risk { background: var(--risk-high); }
.rail.ok { background: var(--risk-low); }
.body { flex: 1; min-width: 0; }
.line1 {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
.ref { font-size: 0.9rem; }
.status { text-transform: uppercase; font-size: 0.68rem; letter-spacing: 0.06em; }
.line2 { font-size: 0.85rem; margin-top: 0.15rem; }
.line3 { font-size: 0.72rem; margin-top: 0.25rem; }
.empty {
  color: var(--text-dim);
  font-size: 0.85rem;
  padding: 1rem;
  border: 1px dashed var(--line);
  border-radius: 8px;
}
</style>
