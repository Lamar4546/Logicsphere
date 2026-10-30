<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ shipments: { type: Array, required: true }, selectedId: { type: String, default: null }, evaluatingId: { type: String, default: null } })
const emit = defineEmits(['evaluate', 'select', 'track'])
const filter = ref('all')
const filters = [
  { id: 'all', label: 'All' }, { id: 'in_transit', label: 'In transit' }, { id: 'at_risk', label: 'At risk' },
  { id: 'delayed', label: 'Delayed' }, { id: 'delivered', label: 'Delivered' },
]
const normalizedStatus = (status) => String(status || '').toLowerCase().replaceAll(' ', '_')
const visible = computed(() => filter.value === 'all' ? props.shipments : props.shipments.filter((shipment) => normalizedStatus(shipment.status) === filter.value))

function eta(value) { return value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—' }
function delay(shipment) {
  if (normalizedStatus(shipment.status) === 'delivered') return '—'
  if (!shipment.eta_original || !shipment.eta_current) return '—'
  const hours = (new Date(shipment.eta_current) - new Date(shipment.eta_original)) / 3600000
  return hours > 0 ? `+${hours >= 1 ? hours.toFixed(1).replace(/\.0$/, '') : hours.toFixed(2)}h` : 'On time'
}
function stateLabel(status) { return normalizedStatus(status).replaceAll('_', ' ').toUpperCase() }

function statusClass(status) {
  return { at_risk: 'at_risk', delayed: 'delayed', in_transit: 'ok', delivered: 'ok' }[normalizedStatus(status)] || 'neutral'
}
</script>

<template>
  <section class="shipment-table-wrap">
    <header class="filterbar"><div class="filters"><button v-for="entry in filters" :key="entry.id" :class="{ active: filter === entry.id }" @click="filter = entry.id">{{ entry.label }}</button></div><span class="record-count">Showing {{ visible.length }} of {{ shipments.length }} shipments</span></header>
    <p v-if="!shipments.length" class="empty">No shipments yet — add one above.</p>
    <p v-else-if="!visible.length" class="empty">No shipments match this status filter.</p>
    <div v-else class="table-scroll"><table><thead><tr><th>Reference</th><th>Route</th><th>Carrier</th><th>Status</th><th>ETA current</th><th>Delay</th><th>Last event</th><th>Action</th></tr></thead><tbody>
      <tr v-for="s in visible" :key="s.id" :class="{ selected: s.id === selectedId }" @click="emit('select', s)">
        <td data-label="Reference"><strong>{{ s.reference_number || '—' }}</strong></td><td data-label="Route">{{ s.origin || '—' }} → {{ s.destination || '—' }}</td><td data-label="Carrier">{{ s.carrier || s.carrier_name || '—' }}</td>
        <td data-label="Status"><span class="status-pill" :class="statusClass(s.status)">{{ stateLabel(s.status) }}</span></td><td data-label="ETA current">{{ eta(s.eta_current) }}</td><td data-label="Delay" :class="delay(s).startsWith('+') ? 'late' : ''">{{ delay(s) }}</td><td class="event" data-label="Last event">{{ s.last_event_description || 'No event reported' }}</td>
        <td data-label="Action"><button class="inspect" @click.stop="emit('track', s)">Inspect</button><button class="evaluate" :disabled="evaluatingId === s.id" @click.stop="emit('evaluate', s)">{{ evaluatingId === s.id ? 'Evaluating…' : 'Evaluate' }}</button></td>
      </tr>
    </tbody></table></div>
  </section>
</template>

<style scoped>
.shipment-table-wrap{overflow:hidden;background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:none}.filterbar{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:.9rem 1rem;border-bottom:1px solid var(--line)}.filters{display:flex;gap:.4rem;flex-wrap:wrap}.filters button{min-height:2.2rem;padding:.38rem .75rem;border:0;border-radius:999px;background:var(--panel-2);color:var(--text-dim);font-size:.75rem;text-transform:uppercase}.filters button.active{background:#2563eb;color:white}.record-count{font-size:.75rem;color:var(--text-dim);white-space:nowrap}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.78rem;text-align:left}th{background:var(--panel-2);color:var(--text-dim);font-size:.68rem;text-transform:uppercase;letter-spacing:.03em;white-space:nowrap}th,td{padding:.85rem .8rem;border-bottom:1px solid var(--line)}td{white-space:nowrap}tbody tr:last-child td{border-bottom:0}tbody tr{cursor:pointer}tbody tr:hover,tbody tr.selected{background:color-mix(in srgb,var(--signal) 5%,var(--panel))}.status-pill{display:inline-block;padding:.25rem .45rem;border-radius:7px;border:1px solid var(--line);font-size:.66rem;font-weight:700}.status-pill.at_risk{color:#b45309;border-color:#fed7aa;background:#fff7ed}.status-pill.delayed{color:#dc2626;border-color:#fecaca;background:#fef2f2}.status-pill.ok{color:#047857;border-color:#a7f3d0;background:#ecfdf5}.status-pill.neutral{color:#475569;background:#f1f5f9}.late{color:var(--risk-critical);font-weight:650}.event{max-width:260px;overflow:hidden;text-overflow:ellipsis;color:var(--text-dim)}.inspect,.evaluate{padding:0;border:0;background:transparent;color:#2563eb;font-size:.75rem;font-weight:600;min-height:auto}.evaluate{display:inline-block;margin-left:.45rem;color:var(--text-dim)}.empty{color:var(--text-dim);font-size:.85rem;padding:1rem;border:1px dashed var(--line);border-radius:8px}
.empty {
  color: var(--text-dim);
  font-size: 0.85rem;
  padding: 1rem;
  border: 1px dashed var(--line);
  border-radius: 8px;
}
@media(max-width:900px){table{min-width:1050px}}@media(max-width:600px){.filterbar{align-items:flex-start;flex-direction:column}.record-count{font-size:.68rem}table{min-width:1000px}}
</style>
