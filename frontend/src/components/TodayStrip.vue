<script setup>
import { computed } from 'vue'

const props = defineProps({ today: { type: Object, required: true }, shipments: { type: Array, default: () => [] } })

const active = computed(() => props.shipments.filter((s) => !['delivered', 'cancelled'].includes(s.status)))
const activeCount = computed(() => active.value.length)

// On time = current ETA is no more than 15 minutes later than the original ETA.
const onTimeRate = computed(() => {
  const timed = active.value.filter((s) => s.eta_original && s.eta_current)
  if (!timed.length) return null
  const onTime = timed.filter((s) => new Date(s.eta_current) - new Date(s.eta_original) <= 15 * 60000).length
  return Math.round((100 * onTime) / timed.length)
})

const share = (n) => (activeCount.value ? Math.min(100, Math.round((100 * n) / activeCount.value)) : 0)
const cards = computed(() => [
  { label: 'Active shipments', value: activeCount.value, icon: '▦', tone: 'signal', fill: 100 },
  { label: 'On-time rate', value: onTimeRate.value === null ? '—' : `${onTimeRate.value}%`, icon: '✓', tone: 'ok', fill: onTimeRate.value ?? 0 },
  { label: 'At-risk shipments', value: props.today.at_risk_count, icon: '⚠', tone: 'warn', fill: share(props.today.at_risk_count) },
  { label: 'Pending approvals', value: props.today.pending_approvals_count, icon: '◷', tone: 'signal', fill: Math.min(100, props.today.pending_approvals_count * 20) },
])
</script>

<template>
  <div class="strip">
    <div v-for="c in cards" :key="c.label" class="stat panel">
      <span class="icon" :class="c.tone">{{ c.icon }}</span>
      <span class="mono dim label">{{ c.label }}</span>
      <span class="value display">{{ c.value }}</span>
      <span class="bar"><i :class="c.tone" :style="{ width: c.fill + '%' }"></i></span>
    </div>
  </div>
</template>

<style scoped>
.strip { display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 1rem; margin:1.15rem 0; }
.stat { position:relative;padding: 1.15rem 1.15rem 1rem; display: flex; flex-direction: column; gap: .35rem; min-width: 160px;border-radius:18px;box-shadow:none }
.icon { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border-radius: 12px; font-size: 1.05rem; margin-bottom: .35rem;position:absolute;right:1rem;top:1rem;border:1px solid var(--line) }
.icon.signal { color: var(--signal); background: color-mix(in srgb, var(--signal) 14%, transparent); }
.icon.ok { color: var(--risk-low); background: color-mix(in srgb, var(--risk-low) 14%, transparent); }
.icon.warn { color: var(--risk-high); background: color-mix(in srgb, var(--risk-high) 14%, transparent); }
.label { font-size: .7rem; text-transform: uppercase; letter-spacing: .03em;font-family:var(--font-body);font-weight:700;margin:.45rem 3rem .55rem 0 }
.value { font-size: 1.9rem; font-weight: 600; color: var(--text); }
.bar { height: 6px; border-radius: 99px; background: var(--line); overflow: hidden; margin-top: .3rem; }
.bar i { display: block; height: 100%; border-radius: 99px; }
.bar i.signal { background: var(--signal); } .bar i.ok { background: var(--risk-low); } .bar i.warn { background: var(--risk-high); }
@media (max-width: 760px) { .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .65rem; width: 100%; } .stat { min-width: 0; padding: .85rem; } .label { font-size: .59rem; line-height: 1.3; } .value { font-size: 1.55rem; } }
</style>
