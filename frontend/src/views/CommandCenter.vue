<script setup>
import { ref, onMounted, onBeforeUnmount, reactive, watch } from 'vue'
import { api } from '../services/api.js'
import TodayStrip from '../components/TodayStrip.vue'
import ShipmentIntakeForm from '../components/ShipmentIntakeForm.vue'
import ShipmentList from '../components/ShipmentList.vue'
import RecommendationCard from '../components/RecommendationCard.vue'
import CommunicationCard from '../components/CommunicationCard.vue'
import ProcessProgress from '../components/ProcessProgress.vue'
import ShipmentMap from '../components/ShipmentMap.vue'
import DeliveryInsights from '../components/DeliveryInsights.vue'

const props = defineProps({ initialTab: { type: String, default: 'tracking' } })

const loading = ref(true)
const errorMessage = ref('')
const shipments = ref([])
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
const selectedShipment = ref(null)
const evaluatingId = ref(null)
const process = ref(null)
const notifications = ref([])
const refreshedAt = ref(null)
let refreshTimer

// guards against async work (in-flight fetches, interval ticks) resolving
// after the component has been unmounted and mutating dead reactive state
const isMounted = ref(true)

// prevents overlapping refreshAll() calls if a request takes longer than
// the poll interval
let refreshInFlight = false

watch(() => props.initialTab, (tab) => { activeTab.value = tab })

async function loadNotifications(shipmentId) {
  try {
    const result = await api.listShipmentNotifications(shipmentId)
    if (!isMounted.value) return
    notifications.value = result
  } catch {
    if (!isMounted.value) return
    notifications.value = []
  }
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
    shipments.value = Array.isArray(list) ? list : []
    if (!selectedShipment.value && list.length) selectedShipment.value = list[0]
    if (selectedShipment.value) selectedShipment.value = list.find((shipment) => shipment.id === selectedShipment.value.id) || null
    if (selectedShipment.value) await loadNotifications(selectedShipment.value.id)
    if (!isMounted.value) return

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
  process.value = { referenceNumber: shipment.reference_number, status: 'running', completedStage: 0, label: 'Agents running', detail: 'Reading tracking signals and dispatching the workflow.' }
  try {
    const result = await api.evaluateShipment(shipment.id)
    if (!isMounted.value) return

    const requiresApproval = result.policy?.requires_approval
    process.value = { referenceNumber: shipment.reference_number, status: requiresApproval ? 'waiting' : 'completed', completedStage: 4, label: requiresApproval ? 'Human approval required' : 'Autonomously completed', detail: requiresApproval ? 'Critical or monetary action is waiting in Exceptions.' : 'The agents completed the routine logistics workflow.' }
    await refreshAll()
    if (!isMounted.value) return
    await loadNotifications(shipment.id)
  } catch (err) {
    if (!isMounted.value) return
    errorMessage.value = err.message
    process.value = { referenceNumber: shipment.reference_number, status: 'failed', completedStage: 0, label: 'Evaluation failed', detail: err.message }
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
      <TodayStrip :today="summary.today" :shipments="shipments" />
      <DeliveryInsights :shipments="shipments" />

      <nav class="process-tabs" aria-label="Logistics workflow stages">
        <button :class="{ active: activeTab === 'tracking' }" @click="activeTab = 'tracking'">1. Tracking</button>
        <button :class="{ active: activeTab === 'risk' }" @click="activeTab = 'risk'">2. Risk analysis</button>
        <button :class="{ active: activeTab === 'recommendations' }" @click="activeTab = 'recommendations'">3. Exceptions</button>
        <button :class="{ active: activeTab === 'communications' }" @click="activeTab = 'communications'">4. Autonomous actions</button>
      </nav>

      <section v-if="activeTab === 'tracking'" class="stage">
          <div class="section-heading"><h2 class="section-title">Shipments <span class="dim mono">/ live control</span></h2><button class="refresh" @click="refreshAll">Refresh</button></div>
          <details class="new-shipment"><summary>+ Add or import shipment</summary><ShipmentIntakeForm @created="handleShipmentCreated" /></details>
          <ProcessProgress :process="process" :shipment="selectedShipment" :notifications="notifications" />
          <div class="tracking-layout"><div class="shipment-column"><ShipmentList :shipments="shipments" :selected-id="selectedShipment?.id" :evaluating-id="evaluatingId" @evaluate="handleEvaluate" @select="selectedShipment = $event; loadNotifications($event.id)" /></div><ShipmentMap v-if="selectedShipment" :shipment="selectedShipment" /><div v-else class="panel empty-map">Select a shipment to view its live tracking map and ETA.</div></div>
          <p class="sync-note">{{ refreshedAt ? `Last synced ${refreshedAt.toLocaleTimeString()}` : 'Waiting for shipment data…' }}</p>
      </section>

      <section v-else-if="activeTab === 'risk'" class="stage">
          <h2 class="section-title">Risk analysis <span class="dim mono">/ transportation + risk agents</span></h2>
          <p v-if="!summary.open_alerts.length" class="empty">No open shipment risks. Evaluate a delayed shipment to run the agents.</p>
          <article v-for="alert in summary.open_alerts" :key="alert.id" class="panel risk-card">
            <span class="badge mono">{{ alert.severity }} risk</span>
            <p>{{ alert.description }}</p>
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
.control-shell{min-height:calc(100dvh - 82px);margin:-1.25rem -2rem -2rem;padding:1.5rem 2rem 2rem;background:radial-gradient(circle at 78% 0%,color-mix(in srgb,var(--signal) 14%,transparent) 0,transparent 28%),var(--ink)}
.banner.error {
  border-color: var(--risk-critical);
  color: #FFB4B4;
}

.process-tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1.75rem; border-bottom: 1px solid var(--line); padding-bottom: 0.75rem; }
.process-tabs button { background: transparent; border: 1px solid var(--line); color: var(--text-dim); padding: 0.5rem 0.75rem; border-radius: 6px; }
.process-tabs button.active { background: var(--signal); border-color: var(--signal); color: #fff; }
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
.section-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.refresh{padding:.38rem .62rem;font-size:.73rem}.new-shipment{margin-bottom:1rem}.new-shipment>summary{display:inline-flex;align-items:center;padding:.55rem .8rem;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--signal);cursor:pointer;font-size:.82rem;font-weight:600}.new-shipment[open]>summary{margin-bottom:.7rem}.tracking-layout{display:grid;grid-template-columns:minmax(280px,.75fr) minmax(380px,1.25fr);gap:1rem;align-items:start}.shipment-column{min-width:0}.empty-map{padding:1rem;color:var(--text-dim);min-height:300px}.sync-note{margin:.75rem 0;color:var(--text-dim);font:.67rem var(--font-mono)}@media(max-width:850px){.tracking-layout{grid-template-columns:1fr}.stage{max-width:780px}}
@media(max-width:800px){.control-shell{margin:-1.25rem;padding:1.25rem}.stage{max-width:100%}}
</style>
