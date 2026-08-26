<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../services/api.js'

const props = defineProps({ initialTab: { type: String, default: 'orders' } })
const tab = ref(props.initialTab)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const data = reactive({ orders: [], delivery_tasks: [], inventory: [], returns: [], carrier_assignments: [], financial_records: [], integrations_ready: false })
const order = reactive({ reference_number: '', customer_name: '', origin: '', destination: '', priority: 'standard' })
const item = reactive({ sku: '', name: '', quantity: 0, reorder_point: 0, location: '' })
const returnForm = reactive({ order_id: '', reason: '' })
const assignment = reactive({ order_id: '', carrier_name: '', service_level: 'standard', driver_reference: '', quoted_amount: '' })
const integrationRecord = reactive({ source: 'wms', sku: '', name: '', quantity: 0, reorder_point: 0, location: '', external_id: '', record_type: 'invoice', amount: '', currency: 'USD', status: 'open' })
const importFile = ref(null)
const importing = ref(false)
const lowStock = computed(() => data.inventory.filter((entry) => entry.quantity <= entry.reorder_point))
watch(() => props.initialTab, (nextTab) => { tab.value = nextTab })

async function refresh() {
  loading.value = true; error.value = ''
  try { Object.assign(data, await api.getOperationsOverview()) } catch (err) { error.value = err.message } finally { loading.value = false }
}
async function createOrder() {
  try { const result = await api.createOrder(order); notice.value = result.agent_result.summary; Object.assign(order, { reference_number: '', customer_name: '', origin: '', destination: '', priority: 'standard' }); await refresh() } catch (err) { error.value = err.message }
}
function chooseCsv(event) { importFile.value = event.target.files?.[0] || null }
async function importCsv() {
  if (!importFile.value) { error.value = 'Choose a CSV file first.'; return }
  importing.value = true; error.value = ''; notice.value = ''
  try {
    const result = await api.importOrdersCsv(importFile.value)
    notice.value = `${result.imported} order${result.imported === 1 ? '' : 's'} imported and linked to shipments.${result.failed ? ` ${result.failed} row(s) need attention.` : ''}`
    importFile.value = null; await refresh()
  } catch (err) { error.value = err.message } finally { importing.value = false }
}
async function saveInventory() {
  try { const result = await api.upsertInventory(item); notice.value = result.agent_result.summary; Object.assign(item, { sku: '', name: '', quantity: 0, reorder_point: 0, location: '' }); await refresh() } catch (err) { error.value = err.message }
}
async function createReturn() {
  try { const result = await api.createReturn(returnForm); notice.value = result.agent_result.summary; Object.assign(returnForm, { order_id: '', reason: '' }); await refresh() } catch (err) { error.value = err.message }
}
async function createAssignment() {
  try {
    const payload = { ...assignment }
    if (payload.quoted_amount === '') delete payload.quoted_amount
    else payload.quoted_amount = Number(payload.quoted_amount)
    const result = await api.createCarrierAssignment(payload)
    notice.value = result.status === 'pending_approval' ? 'Assignment saved. A quoted carrier cost requires your confirmation before dispatch.' : 'Assignment saved and ready for your confirmation.'
    Object.assign(assignment, { order_id: '', carrier_name: '', service_level: 'standard', driver_reference: '', quoted_amount: '' }); await refresh()
  } catch (err) { error.value = err.message }
}
async function dispatchAssignment(id) {
  try { const result = await api.dispatchCarrierAssignment(id); notice.value = `Carrier assignment dispatched${result.assignment?.external_assignment_id ? ` (${result.assignment.external_assignment_id})` : ''}.`; await refresh() } catch (err) { error.value = err.message; await refresh() }
}
async function importIntegrationRecord() {
  try {
    const resource = integrationRecord.source === 'wms' ? 'inventory' : 'financial_records'
    const record = resource === 'inventory' ? { sku: integrationRecord.sku, name: integrationRecord.name, quantity: integrationRecord.quantity, reorder_point: integrationRecord.reorder_point, location: integrationRecord.location } : { external_id: integrationRecord.external_id, record_type: integrationRecord.record_type, amount: integrationRecord.amount === '' ? null : Number(integrationRecord.amount), currency: integrationRecord.currency, status: integrationRecord.status }
    const result = await api.syncIntegrationRecords({ integration: integrationRecord.source, resource, records: [record] })
    notice.value = `${result.imported} ${resource === 'inventory' ? 'inventory record' : 'financial record'} imported from ${integrationRecord.source.toUpperCase()}.`; await refresh()
  } catch (err) { error.value = err.message }
}
onMounted(refresh)
</script>

<template>
  <div>
    <div v-if="error" class="banner error">{{ error }}</div><div v-if="notice" class="banner success">{{ notice }}</div>
    <div class="intro"><div><span class="mono dim">AUTONOMOUS CONTROL PLANE</span><h2>Agent-operated logistics</h2><p>The manager delegates routine work to dispatch, tracking, inventory, communications, and reverse-logistics agents. Critical and monetary actions stay in Exceptions.</p></div><button @click="refresh">Refresh</button></div>
    <nav class="tabs"><button v-for="entry in [['orders','Orders & dispatch'],['inventory','Inventory'],['delivery','Tracking & ePOD'],['alerts','Alerts'],['analytics','Analytics'],['returns','Returns']]" :key="entry[0]" :class="{active:tab===entry[0]}" @click="tab=entry[0]">{{ entry[1] }}</button></nav>
    <p v-if="loading" class="banner">Loading operations…</p>
    <template v-else>
      <section v-if="tab==='orders'" class="grid"><form class="panel form" @submit.prevent="createOrder"><h3>Create order → shipment → dispatch</h3><input v-model="order.reference_number" required placeholder="Order reference"/><input v-model="order.customer_name" placeholder="Customer"/><input v-model="order.origin" placeholder="Pickup / origin"/><input v-model="order.destination" placeholder="Delivery destination"/><select v-model="order.priority"><option>standard</option><option>urgent</option></select><button class="primary">Create & dispatch</button><small class="dim">A linked planned shipment is created immediately for the Control Tower.</small></form><form class="panel form" @submit.prevent="importCsv"><h3>Bulk import orders from CSV</h3><input type="file" accept=".csv,text/csv" aria-label="Order CSV file" @change="chooseCsv"/><small class="dim">Required: <strong>reference_number</strong>. Optional: customer_name, origin, destination, priority.</small><button class="primary" :disabled="importing || !importFile">{{ importing ? 'Importing…' : 'Import CSV & create shipments' }}</button></form><form class="panel form" @submit.prevent="createAssignment"><h3>Carrier booking / delivery assignment</h3><select v-model="assignment.order_id" required><option value="" disabled>Select order</option><option v-for="entry in data.orders" :key="entry.id" :value="entry.id">{{ entry.reference_number }}</option></select><input v-model="assignment.carrier_name" required placeholder="Carrier name"/><input v-model="assignment.service_level" placeholder="Service level"/><input v-model="assignment.driver_reference" placeholder="Driver or vehicle reference"/><input v-model="assignment.quoted_amount" type="number" min="0" step=".01" placeholder="Quoted cost (optional)"/><button class="primary">Prepare assignment</button><small class="dim">Dispatch calls your configured carrier connection only after you confirm it.</small></form><div class="panel list span-all"><h3>Carrier assignments</h3><p v-if="!data.carrier_assignments.length" class="dim">No carrier assignments. Apply migration 007 to enable this integration.</p><article v-for="entry in data.carrier_assignments" :key="entry.id"><strong>{{ entry.carrier_name }} · {{ entry.service_level || 'standard' }}</strong><span>{{ entry.status }}</span><p>{{ entry.driver_reference || 'Driver pending' }} · {{ entry.external_assignment_id || 'Not sent to carrier' }}</p><button v-if="entry.status==='ready_to_dispatch'||entry.status==='pending_approval'" @click="dispatchAssignment(entry.id)">Confirm & dispatch</button></article></div></section>
      <section v-else-if="tab==='inventory'" class="grid"><form class="panel form" @submit.prevent="saveInventory"><h3>Inventory / warehouse update</h3><input v-model="item.sku" required placeholder="SKU"/><input v-model="item.name" required placeholder="Item name"/><input v-model.number="item.quantity" type="number" placeholder="Quantity"/><input v-model.number="item.reorder_point" type="number" placeholder="Reorder point"/><input v-model="item.location" placeholder="Shelf / warehouse location"/><button class="primary">Save & evaluate stock</button></form><form class="panel form" @submit.prevent="importIntegrationRecord"><h3>ERP / WMS record import</h3><select v-model="integrationRecord.source"><option value="wms">WMS inventory</option><option value="erp">ERP financial record</option></select><template v-if="integrationRecord.source==='wms'"><input v-model="integrationRecord.sku" required placeholder="External SKU"/><input v-model="integrationRecord.name" required placeholder="Item name"/><input v-model.number="integrationRecord.quantity" type="number" placeholder="Quantity"/><input v-model.number="integrationRecord.reorder_point" type="number" placeholder="Reorder point"/><input v-model="integrationRecord.location" placeholder="Warehouse location"/></template><template v-else><input v-model="integrationRecord.external_id" required placeholder="ERP external record ID"/><input v-model="integrationRecord.record_type" required placeholder="Invoice, bill, credit…"/><input v-model="integrationRecord.amount" type="number" step=".01" placeholder="Amount"/><input v-model="integrationRecord.currency" placeholder="Currency"/><input v-model="integrationRecord.status" placeholder="Record status"/></template><button class="primary">Import source record</button><small class="dim">Financial imports record facts; they cannot create payments or spend.</small></form><div class="panel list span-all"><h3>Inventory exceptions & financial records</h3><p v-if="!lowStock.length && !data.financial_records.length" class="dim">No stock or financial exceptions.</p><article v-for="entry in lowStock" :key="entry.id"><strong>{{ entry.sku }} · {{ entry.name }}</strong><span class="danger">replenishment review</span><p>{{ entry.quantity }} on hand · reorder point {{ entry.reorder_point }}</p></article><article v-for="entry in data.financial_records" :key="entry.id"><strong>{{ entry.record_type }} · {{ entry.document_number || entry.external_id }}</strong><span>{{ entry.status || 'recorded' }}</span><p>{{ entry.amount ?? '—' }} {{ entry.currency }}</p></article></div></section>
      <section v-else-if="tab==='delivery'" class="panel full"><h3>Tracking, route planning & electronic proof of delivery</h3><p>Use the <strong>Shipments</strong> workspace to view live route details, carrier events, ETAs, and the agent evaluation timeline. Delivery tasks below are created automatically when an order is received.</p><article v-for="task in data.delivery_tasks" :key="task.id"><strong>{{ task.assigned_driver }}</strong><span>{{ task.status }}</span><p>{{ task.route_plan?.origin || 'Origin' }} → {{ task.route_plan?.destination || 'Destination' }}</p></article></section>
      <section v-else-if="tab==='alerts'" class="panel full"><h3>Automated alerts & communication</h3><p>Delay events trigger MiniMax-assisted customer updates automatically. Critical risks and financial commitments appear in the Shipments workspace’s <strong>Exceptions</strong> tab for a human decision.</p><div class="agent-grid"><span>Transportation Agent</span><span>Risk Agent</span><span>Communication Agent</span><span>Central Manager</span></div></section>
      <section v-else-if="tab==='analytics'" class="metrics"><div class="panel"><span class="dim mono">ORDERS</span><strong>{{ data.orders.length }}</strong></div><div class="panel"><span class="dim mono">AUTO-DISPATCHED</span><strong>{{ data.delivery_tasks.length }}</strong></div><div class="panel"><span class="dim mono">LOW STOCK</span><strong>{{ lowStock.length }}</strong></div><div class="panel"><span class="dim mono">RETURNS</span><strong>{{ data.returns.length }}</strong></div></section>
      <section v-else class="grid"><form class="panel form" @submit.prevent="createReturn"><h3>Start return → agent route</h3><select v-model="returnForm.order_id"><option value="">No linked order</option><option v-for="entry in data.orders" :key="entry.id" :value="entry.id">{{ entry.reference_number }}</option></select><textarea v-model="returnForm.reason" placeholder="Reason for return"></textarea><button class="primary">Create return workflow</button></form><div class="panel list"><h3>Return workflows</h3><p v-if="!data.returns.length" class="dim">No returns.</p><article v-for="entry in data.returns" :key="entry.id"><strong>{{ entry.reason || 'Return request' }}</strong><span>{{ entry.status }}</span></article></div></section>
    </template>
  </div>
</template>

<style scoped>
.intro { display:flex; justify-content:space-between; gap:1rem; align-items:start; }.intro h2 { font-size:1.25rem; margin-top:.2rem; }.intro p { color:var(--text-dim); max-width:700px; font-size:.86rem; line-height:1.5; }.intro .mono { font-size:.66rem; letter-spacing:.09em; }.tabs { display:flex; flex-wrap:wrap; gap:.5rem; margin:1rem 0; }.tabs button.active { background:var(--signal); color:#fff; border-color:var(--signal); }.grid { display:grid; grid-template-columns:repeat(3,minmax(240px,1fr)); gap:1rem; }.span-all{grid-column:1/-1}.form,.list,.full { padding:1rem; }.form { display:flex; flex-direction:column; gap:.6rem; }.form h3,.list h3,.full h3 { margin:0 0 .4rem; font-size:.95rem; }.form small{line-height:1.4}.list article,.full article { border-top:1px solid var(--line); padding:.75rem 0; }.list span,.full span { float:right; font: .65rem var(--font-mono); text-transform:uppercase; color:var(--text-dim); }.list p,.full p { margin:.3rem 0 .55rem; color:var(--text-dim); font-size:.8rem; }.list article button{padding:.38rem .55rem;font-size:.72rem}.danger { color:var(--risk-critical)!important; }.banner { padding:.7rem .9rem; border:1px solid var(--line); background:var(--panel); border-radius:7px; margin-bottom:.8rem; }.banner.error { color:#ffb4b4; border-color:var(--risk-critical); }.banner.success { color:#b7e9c8; border-color:var(--risk-low); }.metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:1rem; }.metrics div { padding:1rem; display:flex; flex-direction:column; gap:.4rem; }.metrics span { font-size:.65rem; }.metrics strong { font: 2rem var(--font-display); color:var(--signal); }.agent-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:.6rem; margin-top:1rem; }.agent-grid span { padding:.75rem; border:1px solid var(--line); border-radius:6px; float:none; text-align:center; } @media(max-width:900px){.grid{grid-template-columns:1fr 1fr}}@media(max-width:650px){.grid{grid-template-columns:1fr}.span-all{grid-column:auto}.metrics,.agent-grid{grid-template-columns:1fr 1fr}}
</style>
