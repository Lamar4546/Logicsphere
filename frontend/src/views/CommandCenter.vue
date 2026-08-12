<script setup>
import { ref, onMounted, reactive } from 'vue'
import { api } from '../services/api.js'
import TodayStrip from '../components/TodayStrip.vue'
import ShipmentIntakeForm from '../components/ShipmentIntakeForm.vue'
import ShipmentList from '../components/ShipmentList.vue'
import RecommendationCard from '../components/RecommendationCard.vue'
import CommunicationCard from '../components/CommunicationCard.vue'

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

async function refreshAll() {
  errorMessage.value = ''
  try {
    const [s, list] = await Promise.all([
      api.getCommandCenterSummary(),
      api.listShipments(),
    ])
    Object.assign(summary, s)
    shipments.value = list
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    loading.value = false
  }
}

async function handleShipmentCreated() {
  await refreshAll()
}

async function handleEvaluate(shipmentId) {
  errorMessage.value = ''
  try {
    await api.evaluateShipment(shipmentId)
    await refreshAll()
  } catch (err) {
    errorMessage.value = err.message
  }
}

async function handleApprove(recommendationId) {
  errorMessage.value = ''
  try {
    const result = await api.approveRecommendation(recommendationId)
    workflowByRecommendation.value[recommendationId] = result.workflow_id
    await refreshAll()
  } catch (err) {
    errorMessage.value = err.message
  }
}

async function handleReject(recommendationId) {
  errorMessage.value = ''
  try {
    await api.rejectRecommendation(recommendationId)
    await refreshAll()
  } catch (err) {
    errorMessage.value = err.message
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
    await refreshAll()
  } catch (err) {
    errorMessage.value = err.message
  }
}

onMounted(refreshAll)
</script>

<template>
  <div>
    <div v-if="errorMessage" class="banner error">{{ errorMessage }}</div>
    <div v-if="loading" class="banner">Loading command center…</div>

    <template v-else>
      <TodayStrip :today="summary.today" />

      <section class="grid">
        <div class="col">
          <h2 class="section-title">Shipments <span class="dim mono">/ 10.1 onboarding stand-in</span></h2>
          <ShipmentIntakeForm @created="handleShipmentCreated" />
          <ShipmentList :shipments="shipments" @evaluate="handleEvaluate" />
        </div>

        <div class="col">
          <h2 class="section-title">AI Recommendations <span class="dim mono">/ pending approval</span></h2>
          <p v-if="!summary.ai_recommendations.length" class="empty">
            No recommendations pending. Evaluate an at-risk shipment to generate one.
          </p>
          <RecommendationCard
            v-for="rec in summary.ai_recommendations"
            :key="rec.id"
            :recommendation="rec"
            @approve="handleApprove"
            @reject="handleReject"
          />

          <h2 class="section-title" style="margin-top: 1.75rem;">
            Communications <span class="dim mono">/ draft — needs approval</span>
          </h2>
          <p v-if="!summary.pending_communications.length" class="empty">
            No drafted communications yet.
          </p>
          <CommunicationCard
            v-for="comm in summary.pending_communications"
            :key="comm.id"
            :communication="comm"
            @send="handleSendCommunication"
          />
        </div>
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
.banner.error {
  border-color: var(--risk-critical);
  color: #FFB4B4;
}

.grid {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 1.75rem;
  margin-top: 1.75rem;
  align-items: start;
}

@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
}

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
</style>
