<script setup>
import CommandCenter from './views/CommandCenter.vue'
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">LS</span>
        <div>
          <h1 class="display">LogiSphere AI</h1>
          <span class="dim eyebrow">Command Center — Shipment Delay Workflow</span>
        </div>
      </div>
      <div class="status-chip">
        <span class="pulse"></span> Central AI Logistics Manager · Online
      </div>
    </header>
    <main>
      <CommandCenter />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 2rem;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, var(--panel) 0%, var(--ink) 100%);
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}

.brand-mark {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.8rem;
  color: #1A1200;
  background: var(--signal);
  border-radius: 6px;
  padding: 0.4rem 0.55rem;
  letter-spacing: 0.04em;
}

h1 {
  font-size: 1.25rem;
  font-weight: 600;
}

.eyebrow {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-dim);
}

.pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--risk-low);
  box-shadow: 0 0 0 rgba(78, 159, 110, 0.6);
  animation: pulse 2.2s infinite;
}

@keyframes pulse {
  0%   { box-shadow: 0 0 0 0 rgba(78, 159, 110, 0.55); }
  70%  { box-shadow: 0 0 0 8px rgba(78, 159, 110, 0); }
  100% { box-shadow: 0 0 0 0 rgba(78, 159, 110, 0); }
}

main {
  flex: 1;
  padding: 1.75rem 2rem 3rem;
  max-width: 1180px;
  width: 100%;
  margin: 0 auto;
}
</style>
