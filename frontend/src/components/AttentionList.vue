<script setup>
import { computed } from 'vue'

const props = defineProps({ shipments: { type: Array, default: () => [] } })
const emit = defineEmits(['review', 'view-all'])

const rank = (s) => (s.status === 'delayed' ? 0 : 1)
const flaggedAll = computed(() => props.shipments.filter((s) => ['delayed', 'at_risk'].includes(s.status)))
const flagged = computed(() => [...flaggedAll.value].sort((a, b) => rank(a) - rank(b)).slice(0, 3))
</script>

<template>
  <section v-if="flagged.length" class="attention">
    <div class="heading">
      <h2>Needs your attention</h2>
      <button class="ghost link" type="button" @click="emit('view-all')">View all ({{ flaggedAll.length }})</button>
    </div>
    <article v-for="s in flagged" :key="s.id" class="panel item" :class="s.status">
      <span class="tag mono">{{ s.status === 'delayed' ? 'Delayed' : 'At risk' }}</span>
      <div class="info">
        <div><strong class="mono">{{ s.reference_number }}</strong> <span class="dim route">{{ s.origin || '—' }} → {{ s.destination || '—' }}</span></div>
        <p class="dim">{{ s.last_event_description || 'Open this shipment to see what the agents found.' }}</p>
      </div>
      <button class="primary" type="button" @click="emit('review', s)">Review action</button>
    </article>
  </section>
</template>

<style scoped>
.attention { margin-bottom: 1.15rem; }
.heading { display: flex; justify-content: space-between; align-items: center; margin-bottom: .6rem; }
.heading h2 { font-size: .9rem; text-transform:uppercase;letter-spacing:.04em;color:var(--text-dim) }
.link { border: 0; color: var(--signal); font-size: .75rem; padding: .2rem .3rem; }
.item { display: flex; align-items: center; gap: 1rem; padding: .8rem 1rem; margin-bottom: .55rem; border-radius:14px;box-shadow:none }
.tag { font-size: .68rem; text-transform: uppercase; letter-spacing: .02em; padding: .32rem .55rem; border-radius: 7px; color: #b45309; background: #fff7ed; border:1px solid #fed7aa;white-space: nowrap; }
.item.delayed .tag { color: #dc2626; background: #fef2f2;border-color:#fecaca }
.info { flex: 1; min-width: 0; }
.info p { margin: .2rem 0 0; font-size: .8rem; }
.route { font-size: .8rem; margin-left: .35rem; }
@media (max-width: 600px) { .item { flex-wrap: wrap; } .info { flex-basis: 100%; order: 3; } .item button{margin-left:auto} }
</style>
