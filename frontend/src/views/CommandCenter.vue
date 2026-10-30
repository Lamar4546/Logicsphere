<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount, reactive, watch, computed, defineAsyncComponent } from 'vue'
import { api } from '../services/api.js'
import TodayStrip from '../components/TodayStrip.vue'
import ShipmentIntakeForm from '../components/ShipmentIntakeForm.vue'
import ShipmentList from '../components/ShipmentList.vue'
import RecommendationCard from '../components/RecommendationCard.vue'
import CommunicationCard from '../components/CommunicationCard.vue'
import FleetOverviewMap from '../components/FleetOverviewMap.vue'
import AttentionList from '../components/AttentionList.vue'
const FleetGlobe = defineAsyncComponent(() => import('../components/FleetGlobe.vue'))
const props = defineProps({ initialTab: { type: String, default: 'tracking' }, searchQuery: { type: String, default: '' } })
const emit = defineEmits(['pending-approvals'])

const loading = ref(true)
const errorMessage = ref('')
const shipments = ref([])
const visibleShipments = computed(() => {
  const query = props.searchQuery.trim().toLocaleLowerCase()
  if (!query) return shipments.value
  return shipments.value.filter((shipment) => [shipment.reference_number, shipment.origin, shipment.destination, shipment.carrier, shipment.transport_mode, shipment.driver_name, shipment.driver_reference, shipment.vehicle_id, shipment.current_location_name].some((value) => String(value || '').toLocaleLowerCase().includes(query)))
})
const recentActivity = computed(() => [...shipments.value]
  .filter((shipment) => shipment.last_event_description)
  .sort((a, b) => new Date(b.tracking_updated_at || b.updated_at || 0) - new Date(a.tracking_updated_at || a.updated_at || 0))
  .slice(0, 4))
const summary = reactive({
  today: { at_risk_count: 0, pending_approvals_count: 0 },
  at_risk_shipments: [],
  open_alerts: [],
  ai_recommendations: [],
  pending_communications: [],
})

// tracks workflow_id per recommendation once approved, so the communication
// card knows which workflow to complete on final send.
const workflowByRecommendation = ref({})
const activeTab = ref(props.initialTab)
const fleetMode = ref('3d')
const selectedShipment = ref(null)
const fleetSection = ref(null)
const evaluatingId = ref(null)
const refreshedAt = ref(null)
const publicTrackingUrl = ref('')
const creatingTrackingLink = ref(false)
let refreshTimer

// guards against async work (in-flight fetches, interval ticks) resolving
// after the component has been unmounted and mutating dead reactive state
const isMounted = ref(true)

// prevents overlapping refreshAll() calls if a request takes longer than
// the poll interval
let refreshInFlight = false

watch(() => props.initialTab, (tab) => { activeTab.value = tab })
// Picking a shipment anywhere (fleet map, attention list) jumps to its tracking view
function focusShipment(shipment) {
  selectedShipment.value = shipment
}
async function handleTrackShipment(shipment) {
  selectedShipment.value = shipment
  publicTrackingUrl.value = ''
  activeTab.value = 'tracking'
  fleetMode.value = '3d'
  await nextTick()
  fleetSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
async function createTrackingLink() {
  if (!selectedShipment.value) return
  creatingTrackingLink.value = true
  errorMessage.value = ''
  try { const result = await api.createPublicTrackingLink(selectedShipment.value.id); publicTrackingUrl.value = new URL(result.tracking_path, window.location.origin).href }
  catch (err) { errorMessage.value = err.message } finally { creatingTrackingLink.value = false }
}
async function copyTrackingLink() {
  try { await navigator.clipboard.writeText(publicTrackingUrl.value) } catch { errorMessage.value = 'Copy was blocked. Select and copy the tracking link manually.' }
}
async function refreshAll() {
  if (refreshInFlight) return
  refreshInFlight = true
  errorMessage.value = ''
  try {
    const [s, list] = await Promise.all([
      api.getCommandCenterSummary(),
      api.listShipments(),
    ])
    if (!isMounted.value) return

    Object.assign(summary, s)
    emit('pending-approvals', Number(s.today?.pending_approvals_count || 0))
    shipments.value = Array.isArray(list) ? list : []
    if (!selectedShipment.value && list.length) selectedShipment.value = list[0]
    if (selectedShipment.value) selectedShipment.value = list.find((shipment) => shipment.id === selectedShipment.value.id) || null
    workflowByRecommendation.value = Object.fromEntries(
      (s.pending_communications || [])
        .filter((communication) => communication.workflow_id)
        .map((communication) => [communication.recommendation_id, communication.workflow_id])
    )
  } catch (err) {
    if (isMounted.value) errorMessage.value = err.message
  } finally {
    if (isMounted.value) {
      loading.value = false
      refreshedAt.value = new Date()
    }
    refreshInFlight = false
  }
}

async function handleShipmentCreated() {
  await refreshAll()
}

async function handleEvaluate(shipment) {
  errorMessage.value = ''
  evaluatingId.value = shipment.id
  try {
    await api.evaluateShipment(shipment.id)
    if (!isMounted.value) return
    await refreshAll()
  } catch (err) {
    if (!isMounted.value) return
    errorMessage.value = err.message
  } finally {
    if (isMounted.value) evaluatingId.value = null
  }
}

async function handleApprove(recommendationId) {
  errorMessage.value = ''
  try {
    const result = await api.approveRecommendation(recommendationId)
    if (!isMounted.value) return
    workflowByRecommendation.value[recommendationId] = result.workflow_id
    await refreshAll()
  } catch (err) {
    if (isMounted.value) errorMessage.value = err.message
  }
}

async function handleReject(recommendationId) {
  errorMessage.value = ''
  try {
    await api.rejectRecommendation(recommendationId)
    if (!isMounted.value) return
    await refreshAll()
  } catch (err) {
    if (isMounted.value) errorMessage.value = err.message
  }
}

async function handleSendCommunication({ communicationId, recommendationId }) {
  errorMessage.value = ''
  const workflowId = workflowByRecommendation.value[recommendationId]
  if (!workflowId) {
    errorMessage.value = 'No workflow linked to this communication yet — approve the recommendation first.'
    return
  }
  try {
    await api.approveCommunicationAndExecute(workflowId, communicationId)
    if (!isMounted.value) return
    await refreshAll()
  } catch (err) {
    if (isMounted.value) errorMessage.value = err.message
  }
}

onMounted(() => {
  refreshAll()
  refreshTimer = window.setInterval(refreshAll, 15000)
})

onBeforeUnmount(() => {
  isMounted.value = false
  window.clearInterval(refreshTimer)
})
</script>
<template>
  <div class="control-shell">
    <div v-if="errorMessage" class="banner error">{{ errorMessage }}</div>
    <div v-if="loading" class="banner">Loading command center…</div>

    <template v-else>
      <section v-if="activeTab==='shipments'" class="stage shipments-page"><div class="section-heading"><div><h2 class="section-title">Shipments</h2><p class="dim">Search, inspect, track, and evaluate shipments.</p></div><div class="heading-actions"><button class="refresh" :disabled="!selectedShipment || creatingTrackingLink" @click="createTrackingLink">{{ creatingTrackingLink ? 'Creating link…' : 'Share tracking link' }}</button><button class="refresh" @click="refreshAll">Refresh</button></div></div><ShipmentList :shipments="visibleShipments" :selected-id="selectedShipment?.id" :evaluating-id="evaluatingId" @evaluate="handleEvaluate" @select="selectedShipment = $event; publicTrackingUrl = ''" @track="handleTrackShipment" /><div v-if="publicTrackingUrl" class="share-link panel"><label for="public-track-link">Customer tracking link</label><input id="public-track-link" :value="publicTrackingUrl" readonly /><button @click="copyTrackingLink">Copy link</button></div><details class="new-shipment"><summary>+ Add or import shipment</summary><ShipmentIntakeForm @created="handleShipmentCreated" /></details><p class="sync-note">{{ refreshedAt ? `Last synced ${refreshedAt.toLocaleTimeString()}` : 'Waiting for shipment data…' }}</p></section>
      <template v-else-if="activeTab==='tracking'">
      <AttentionList v-if="activeTab==='tracking'" :shipments="shipments" @review="focusShipment" @view-all="activeTab = 'risk'" />
      <TodayStrip v-if="activeTab==='tracking'" :today="summary.today" :shipments="shipments" />
      <section v-if="activeTab==='tracking'" ref="fleetSection" id="gods-eye-view" class="fleet-view"><div class="fleet-switch"><span class="fleet-title"><small>LIVE FLEET DISTRIBUTION</small><strong>Jamaica & Caribbean Fleet Overview</strong></span><div><button :class="{active:fleetMode==='3d'}" @click="fleetMode='3d'">3D globe</button><button :class="{active:fleetMode==='2d'}" @click="fleetMode='2d'">2D map</button></div></div>
        <div class="fleet-dashboard">
          <div class="fleet-map-column"><FleetGlobe v-if="fleetMode==='3d'" :shipments="shipments" :selected-id="selectedShipment?.id" @select="focusShipment" />
            <FleetOverviewMap v-else :shipments="shipments" :selected-id="selectedShipment?.id" @select="focusShipment" /></div>
          <aside class="activity-panel panel"><h3>Recent shipment activity</h3><article v-for="shipment in recentActivity" :key="shipment.id"><span class="activity-icon">↗</span><div><strong>{{ shipment.reference_number || 'Shipment update' }}</strong><p>{{ shipment.last_event_description }}</p><small>{{ shipment.tracking_updated_at ? new Date(shipment.tracking_updated_at).toLocaleString() : shipment.status }}</small></div></article><p v-if="!recentActivity.length" class="activity-empty">Shipment events will appear here when carriers or dispatchers report updates.</p></aside>
        </div>
      </section>
      </template>

      <section v-else-if="activeTab === 'risk'" class="stage queue-page">
          <header class="queue-heading"><div><h2>Alerts &amp; Escalations Queue</h2><p>Shipment exceptions and recommendations requiring review.</p></div><button class="refresh" @click="refreshAll">Refresh</button></header>
          <p v-if="!summary.open_alerts.length && !summary.ai_recommendations.length" class="empty">No open shipment risks or pending recommendations.</p>
          <RecommendationCard v-for="rec in summary.ai_recommendations" :key="`rec-${rec.id}`" :recommendation="rec" @approve="handleApprove" @reject="handleReject" />
          <article v-for="alert in summary.open_alerts" :key="alert.id" class="panel risk-card">
            <div class="risk-card-head"><span class="badge mono">{{ alert.severity }} risk</span><strong>{{ alert.shipment_reference || alert.shipment_id || 'Shipment exception' }}</strong></div>
            <p>{{ alert.description }}</p>
            <button class="ghost link" @click="activeTab='shipments'">View shipment list</button>
          </article>
      </section>

      <section v-else-if="activeTab === 'recommendations'" class="stage">
          <h2 class="section-title">Human exceptions <span class="dim mono">/ critical or monetary only</span></h2>
          <p v-if="!summary.ai_recommendations.length" class="empty">
            No approval needed. Routine shipment work is being handled autonomously.
          </p>
          <RecommendationCard
            v-for="rec in summary.ai_recommendations"
            :key="rec.id"
            :recommendation="rec"
            @approve="handleApprove"
            @reject="handleReject"
          />
      </section>

      <section v-else class="stage">
          <h2 class="section-title" style="margin-top: 1.75rem;">
            Communications <span class="dim mono">/ automatic for routine shipments</span>
          </h2>
          <p v-if="!summary.pending_communications.length" class="empty">
            No exceptional communication awaiting review.
          </p>
          <CommunicationCard
            v-for="comm in summary.pending_communications"
            :key="comm.id"
            :communication="comm"
            @send="handleSendCommunication"
          />
      </section>
    </template>
  </div>
</template>

<style scoped>
.banner {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  margin-bottom: 1.25rem;
  font-family: var(--font-mono);
  font-size: 0.85rem;
}
.control-shell{min-height:calc(100dvh - 64px);padding:0;background:var(--ink)}.fleet-switch{display:flex;align-items:center;justify-content:space-between;gap:.75rem;margin:1.4rem 0 .65rem}.fleet-switch>div{display:flex;gap:.35rem}.fleet-switch button{padding:.35rem .65rem;font-size:.72rem;color:var(--text-dim)}.fleet-switch button.active{background:var(--signal);border-color:var(--signal);color:white}.fleet-title{display:grid;gap:.18rem}.fleet-title small{font-size:.64rem;color:var(--text-dim);font-weight:700;letter-spacing:.03em}.fleet-title strong{font-size:1rem}.fleet-dashboard{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(275px,.85fr);gap:1rem;align-items:stretch}.fleet-map-column{min-width:0}.fleet-map-column :deep(.globe-panel),.fleet-map-column :deep(.fleet){height:100%;margin:0}.activity-panel{padding:1rem;min-width:0}.activity-panel h3{font-size:.85rem;padding-bottom:.7rem;border-bottom:1px solid var(--line)}.activity-panel article{display:grid;grid-template-columns:2rem minmax(0,1fr);gap:.65rem;padding:.9rem 0;border-bottom:1px solid var(--line)}.activity-icon{display:grid;place-items:center;width:2rem;height:2rem;border:1px solid color-mix(in srgb,var(--signal) 35%,var(--line));border-radius:9px;color:var(--signal);background:color-mix(in srgb,var(--signal) 8%,white)}.activity-panel article strong{font-size:.76rem}.activity-panel article p{font-size:.75rem;line-height:1.45;margin:.25rem 0;color:var(--text)}.activity-panel article small{font-size:.67rem;color:var(--text-dim)}.activity-empty{font-size:.78rem;line-height:1.5;color:var(--text-dim);padding:.8rem 0}
.banner.error {
  border-color: var(--risk-critical);
  color: #FFB4B4;
}

.stage { margin-top: 1.25rem; max-width: 1180px; }
.risk-card { padding: 1rem; margin-bottom: 0.75rem; }
.risk-card p { margin: 0.65rem 0 0; }
.badge { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); border: 1px solid var(--line); border-radius: 999px; padding: 0.15rem 0.55rem; }

.section-title {
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}
.section-title .mono { font-size: 0.7rem; }

.empty {
  color: var(--text-dim);
  font-size: 0.85rem;
  padding: 1rem;
  border: 1px dashed var(--line);
  border-radius: 8px;
}
.section-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.heading-actions{display:flex;gap:.4rem}.refresh{padding:.38rem .62rem;font-size:.73rem}.share-link{display:grid;grid-template-columns:1fr auto;gap:.4rem .6rem;align-items:center;padding:.75rem;margin-bottom:.75rem}.share-link label{grid-column:1/-1;font-size:.75rem;color:var(--text-dim)}.share-link input{min-width:0}.share-link button{white-space:nowrap}.new-shipment{margin-bottom:1rem}.new-shipment>summary{display:inline-flex;align-items:center;padding:.55rem .8rem;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--signal);cursor:pointer;font-size:.82rem;font-weight:600}.new-shipment[open]>summary{margin-bottom:.7rem}.tracking-layout{display:grid;grid-template-columns:minmax(280px,.75fr) minmax(380px,1.25fr);gap:1rem;align-items:start}.shipment-column{min-width:0}.empty-map{padding:1rem;color:var(--text-dim);min-height:300px}.sync-note{margin:.75rem 0;color:var(--text-dim);font:.67rem var(--font-mono)}@media(max-width:850px){.tracking-layout{grid-template-columns:1fr}.stage{max-width:780px}}@media(max-width:500px){.section-heading{align-items:flex-start;flex-direction:column}.heading-actions{width:100%}.share-link{grid-template-columns:1fr}.share-link label{grid-column:auto}.share-link button{width:100%}}
@media(max-width:900px){.fleet-dashboard{grid-template-columns:1fr}.activity-panel{display:grid;grid-template-columns:1fr 1fr;column-gap:.75rem}.activity-panel h3,.activity-empty{grid-column:1/-1}}@media(max-width:800px){.control-shell{padding:0;overflow:hidden}.stage{max-width:100%}.section-heading{align-items:flex-start}.heading-actions{display:flex;gap:.4rem;flex-wrap:wrap}.new-shipment>summary{font-size:.75rem}}@media(max-width:600px){.control-shell{padding:0}.fleet-switch{align-items:flex-start;flex-direction:column}.fleet-switch>div{width:100%}.fleet-switch button{flex:1}.activity-panel{display:block}}@media(max-width:390px){.section-heading{flex-wrap:wrap}.heading-actions{width:100%}.heading-actions button{flex:1}.refresh{font-size:.7rem}}
</style>
