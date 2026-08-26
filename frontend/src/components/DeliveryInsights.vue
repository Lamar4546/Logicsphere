<script setup>
import { computed } from 'vue'

const props = defineProps({ shipments: { type: Array, default: () => [] } })
const buckets = computed(() => {
  const counts = { delivered: 0, transit: 0, delayed: 0, exception: 0 }
  props.shipments.forEach((shipment) => {
    const status = String(shipment.status || '').toLowerCase()
    if (status === 'delivered') counts.delivered += 1
    else if (['at_risk', 'delayed'].includes(status)) counts.delayed += 1
    else if (['exception', 'cancelled'].includes(status)) counts.exception += 1
    else counts.transit += 1
  })
  return counts
})
const total = computed(() => Object.values(buckets.value).reduce((sum, value) => sum + value, 0))
const onSchedule = computed(() => buckets.value.delivered + buckets.value.transit)
const performance = computed(() => total.value ? Math.round((onSchedule.value / total.value) * 100) : 0)
const donutStyle = computed(() => {
  if (!total.value) return { background: 'conic-gradient(var(--line) 0 100%)' }
  const colors = ['#4aa4ec', '#43c999', '#ef8838', '#ff6674']
  const values = [buckets.value.delivered, buckets.value.transit, buckets.value.delayed, buckets.value.exception]
  let point = 0
  const stops = values.map((value, index) => { const start = point; point += value / total.value * 100; return `${colors[index]} ${start}% ${point}%` })
  return { background: `conic-gradient(${stops.join(',')})` }
})
const items = computed(() => [
  ['Delivered', buckets.value.delivered, 'delivered'], ['In transit', buckets.value.transit, 'transit'],
  ['Delayed / at risk', buckets.value.delayed, 'delayed'], ['Exception', buckets.value.exception, 'exception'],
])
</script>

<template>
  <section class="insights" aria-label="Delivery performance and shipment status">
    <article class="panel performance">
      <div class="panel-head"><div><span class="mono dim">DELIVERY PERFORMANCE</span><h2>{{ performance }}% on schedule</h2></div><span class="status-pill">Live data</span></div>
      <p>Calculated from the current status of {{ total }} tracked shipment{{ total === 1 ? '' : 's' }}.</p>
      <div class="meter" aria-label="On-schedule delivery percentage"><i :style="{ width: `${performance}%` }"></i></div>
      <div class="performance-foot"><strong>{{ onSchedule }}</strong><span>on schedule</span><span>{{ buckets.delayed + buckets.exception }} need attention</span></div>
    </article>
    <article class="panel status-card">
      <div class="panel-head"><div><span class="mono dim">SHIPMENTS BY STATUS</span><h2>Current mix</h2></div></div>
      <div class="status-body"><div class="donut" :style="donutStyle"><div><strong>{{ total }}</strong><small>tracked</small></div></div><ul><li v-for="item in items" :key="item[2]" :class="item[2]"><i></i><span>{{ item[0] }}</span><strong>{{ item[1] }}</strong></li></ul></div>
    </article>
  </section>
</template>

<style scoped>
.insights{display:grid;grid-template-columns:1.25fr .9fr;gap:1rem;margin-top:1rem;max-width:1180px}.insights .panel{padding:1rem}.panel-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.mono{display:block;font-size:.62rem;letter-spacing:.09em}.panel-head h2{font-size:1rem;margin:.3rem 0 0}.status-pill{border:1px solid var(--risk-low);border-radius:999px;color:var(--risk-low);padding:.25rem .45rem;font-size:.64rem}.performance p{color:var(--text-dim);font-size:.77rem;margin:.8rem 0}.meter{height:.6rem;border-radius:999px;background:var(--panel-2);overflow:hidden;border:1px solid var(--line)}.meter i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--signal),var(--risk-low));transition:width .3s ease}.performance-foot{display:flex;align-items:baseline;gap:.4rem;margin-top:.7rem;font-size:.74rem;color:var(--text-dim)}.performance-foot strong{font-size:1rem;color:var(--text)}.performance-foot span:last-child{margin-left:auto;color:var(--risk-high)}.status-body{display:flex;align-items:center;gap:1rem;margin-top:.8rem}.donut{display:grid;place-items:center;width:112px;height:112px;border-radius:50%;flex:0 0 auto}.donut>div{display:flex;flex-direction:column;justify-content:center;align-items:center;width:72px;height:72px;border-radius:50%;background:var(--panel);font-size:1.2rem}.donut small{color:var(--text-dim);font-size:.62rem}.status-body ul{display:grid;gap:.4rem;list-style:none;padding:0;margin:0;width:100%}.status-body li{display:grid;grid-template-columns:.65rem 1fr auto;align-items:center;gap:.45rem;font-size:.72rem;color:var(--text-dim)}.status-body li i{width:.5rem;height:.5rem;border-radius:50%;background:var(--signal)}.status-body li strong{color:var(--text)}.status-body .transit i{background:var(--risk-low)}.status-body .delayed i{background:var(--risk-high)}.status-body .exception i{background:var(--risk-critical)}@media(max-width:820px){.insights{grid-template-columns:1fr}}@media(max-width:420px){.status-body{gap:.65rem}.donut{width:94px;height:94px}.donut>div{width:60px;height:60px}}
</style>
