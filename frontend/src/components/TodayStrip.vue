<script setup>
import { computed } from 'vue'
const props = defineProps({ today: { type: Object, required: true }, shipments: { type: Array, default: () => [] } })
const active = computed(() => props.shipments.filter((item) => !['delivered', 'cancelled'].includes(item.status)).length)
const inTransit = computed(() => props.shipments.filter((item) => ['in_transit', 'at_risk', 'delayed'].includes(item.status)).length)
</script>

<template>
  <div class="strip">
    <div class="stat panel"><span class="mono dim label">Active shipments</span><span class="value display">{{ active }}</span></div>
    <div class="stat panel"><span class="mono dim label">In transit</span><span class="value display">{{ inTransit }}</span></div>
    <div class="stat panel">
      <span class="mono dim label">At Risk</span>
      <span class="value display">{{ today.at_risk_count }}</span>
    </div>
    <div class="stat panel">
      <span class="mono dim label">Pending Approvals</span>
      <span class="value display">{{ today.pending_approvals_count }}</span>
    </div>
  </div>
</template>

<style scoped>
.strip { display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:1rem; }
.stat {
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 160px;
}
.label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.value {
  font-size: 1.9rem;
  font-weight: 600;
  color: var(--signal);
}
@media(max-width:760px){.strip{grid-template-columns:1fr 1fr}.stat{min-width:0}}
</style>
