<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ task: { type: Object, required: true }, saving: { type: Boolean, default: false } })
const emit = defineEmits(['close', 'submit'])
const canvas = ref(null)
const recipient = ref('')
const photo = ref('')
const hasSignature = ref(false)
let drawing = false
let context
const shipmentLabel = computed(() => props.task.route_plan?.reference_number || props.task.shipment_id || 'Delivery')

function point(event) {
  const rect = canvas.value.getBoundingClientRect()
  return { x: (event.clientX - rect.left) * canvas.value.width / rect.width, y: (event.clientY - rect.top) * canvas.value.height / rect.height }
}
function start(event) {
  event.preventDefault()
  canvas.value.setPointerCapture(event.pointerId)
  const p = point(event)
  context.beginPath(); context.moveTo(p.x, p.y); drawing = true
}
function draw(event) {
  if (!drawing) return
  const p = point(event)
  context.lineTo(p.x, p.y); context.stroke(); hasSignature.value = true
}
function stop() { drawing = false }
function clearSignature() { context.clearRect(0, 0, canvas.value.width, canvas.value.height); hasSignature.value = false }
function choosePhoto(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (file.size > 1_000_000) { event.target.value = ''; photo.value = ''; return }
  const reader = new FileReader()
  reader.onload = () => { photo.value = String(reader.result || '') }
  reader.readAsDataURL(file)
}
function submit() {
  if (!recipient.value.trim() || !hasSignature.value || props.saving) return
  emit('submit', { recipientName: recipient.value.trim(), signatureDataUrl: canvas.value.toDataURL('image/png'), photoDataUrl: photo.value || null })
}
function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => {
  context = canvas.value.getContext('2d')
  context.strokeStyle = '#173b63'; context.lineWidth = 3; context.lineCap = 'round'; context.lineJoin = 'round'
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="proof-backdrop" @click.self="emit('close')">
    <section class="proof-dialog panel" role="dialog" aria-modal="true" aria-labelledby="proof-title">
      <header><div><span class="mono dim">DELIVERY CONFIRMATION</span><h2 id="proof-title">Record proof of delivery</h2><p>{{ shipmentLabel }}</p></div><button type="button" aria-label="Close" @click="emit('close')">×</button></header>
      <form @submit.prevent="submit">
        <label>Recipient name<input v-model="recipient" maxlength="160" required autocomplete="name" placeholder="Name of person receiving delivery" /></label>
        <div class="signature-label"><label for="signature-pad">Recipient signature</label><button type="button" class="ghost" @click="clearSignature">Clear</button></div>
        <canvas id="signature-pad" ref="canvas" width="720" height="220" aria-label="Sign here" @pointerdown="start" @pointermove="draw" @pointerup="stop" @pointercancel="stop" @pointerleave="stop"></canvas>
        <label>Delivery photo <span class="dim">optional · max 1 MB</span><input type="file" accept="image/png,image/jpeg" @change="choosePhoto" /></label>
        <img v-if="photo" class="photo-preview" :src="photo" alt="Selected delivery evidence" />
        <p class="proof-note">Saving this proof marks the linked shipment and delivery task as delivered.</p>
        <footer><button type="button" @click="emit('close')">Cancel</button><button class="primary" type="submit" :disabled="saving || !recipient.trim() || !hasSignature">{{ saving ? 'Saving…' : 'Save delivery proof' }}</button></footer>
      </form>
    </section>
  </div>
</template>

<style scoped>
.proof-backdrop{position:fixed;inset:0;z-index:60;display:grid;place-items:center;padding:1rem;background:rgba(5,14,24,.68)}.proof-dialog{width:min(560px,100%);max-height:calc(100dvh - 2rem);overflow:auto;padding:1.25rem}.proof-dialog header{display:flex;justify-content:space-between;gap:1rem;margin-bottom:1rem}.proof-dialog header .mono{font-size:.65rem;letter-spacing:.08em}.proof-dialog h2{font-size:1.15rem;margin:.25rem 0}.proof-dialog header p{margin:0;color:var(--text-dim);font-size:.78rem}.proof-dialog form{display:grid;gap:.8rem}.proof-dialog label{display:grid;gap:.35rem;font-size:.78rem}.signature-label{display:flex;align-items:center;justify-content:space-between}.signature-label label{font-size:.78rem}canvas{display:block;width:100%;height:170px;border:1px dashed var(--line);border-radius:9px;background:#fff;touch-action:none}.ghost{padding:.3rem .55rem;font-size:.72rem}.photo-preview{width:100%;max-height:180px;object-fit:contain;border-radius:8px;background:var(--panel-2)}.proof-note{margin:0;color:var(--text-dim);font-size:.72rem;line-height:1.45}.proof-dialog footer{display:flex;justify-content:flex-end;gap:.5rem}.proof-dialog footer button{font-size:.78rem}@media(max-width:500px){.proof-dialog{padding:1rem}.proof-dialog footer{display:grid;grid-template-columns:1fr 1.4fr}.proof-dialog footer button{padding:.5rem}}
</style>
