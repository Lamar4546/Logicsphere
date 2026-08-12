<script setup>
defineProps({ today: { type: Object, required: true } })
</script>

<template>
  <div class="strip">
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
.strip {
  display: flex;
  gap: 1rem;
}
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
</style>
