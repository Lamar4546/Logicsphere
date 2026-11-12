<script setup>
import { computed, reactive, ref } from 'vue'
import { api } from '../services/api.js'

const emit = defineEmits(['created'])
const form = reactive({ tracking_number: '', carrier_slug: '', reference_number: '', origin: '', destination: '', transport_mode: 'truck', live_tracking_id: '' })
const submitting = ref(false)
const error = ref('')
const liveIdHint = computed(() => ({ truck: 'Traccar device unique ID', ship: 'Vessel MMSI (9 digits)', plane: 'Aircraft ICAO24 (6 hex characters)' }[form.transport_mode]))

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const shipment = await api.createPackageTracking({
      tracking_number: form.tracking_number.trim(),
      carrier_slug: form.carrier_slug.trim() || undefined,
      reference_number: form.reference_number.trim() || undefined,
      origin: form.origin.trim() || undefined,
      destination: form.destination.trim() || undefined,
      transport_mode: form.transport_mode,
      live_tracking_id: form.live_tracking_id.trim() || undefined,
    })
    Object.assign(form, { tracking_number: '', carrier_slug: '', reference_number: '', origin: '', destination: '', transport_mode: 'truck', live_tracking_id: '' })
    emit('created', shipment)
  } catch (err) {
    error.value = err.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="panel package-form" @submit.prevent="submit">
    <div>
      <h3>Track a package</h3>
      <p class="dim">Enter the package tracking number. Tracking uses 17TRACK by default and can identify the carrier automatically.</p>
    </div>
    <div class="fields">
      <input v-model="form.tracking_number" placeholder="Package tracking number" required maxlength="128" />
      <input v-model="form.carrier_slug" placeholder="Carrier ID (optional; 17TRACK code / AfterShip slug)" />
      <input v-model="form.reference_number" placeholder="Shipment name / reference (optional)" />
      <input v-model="form.origin" placeholder="Origin (optional)" />
      <input v-model="form.destination" placeholder="Destination (optional)" />
      <select v-model="form.transport_mode" aria-label="Shipment mode"><option value="truck">Land shipment</option><option value="ship">Sea shipment</option><option value="plane">Air shipment</option></select>
      <input v-model="form.live_tracking_id" :placeholder="liveIdHint + ' (optional)'" :aria-label="liveIdHint" />
      <button class="primary" type="submit" :disabled="submitting">{{ submitting ? 'Adding package…' : 'Track package' }}</button>
    </div>
    <p class="dim live-help">Live map positions need the carrier asset ID above: Traccar device ID, vessel MMSI, or aircraft ICAO24. The parcel number supplies carrier scans and delivery status; it usually does not identify the vehicle carrying the item.</p>
    <p v-if="error" class="error">{{ error }}</p>
  </form>
</template>

<style scoped>
.package-form { padding: 1rem; margin: .8rem 0 1rem; display: grid; gap: .7rem; }
h3 { margin: 0; font-size: .9rem; }
.dim { margin: .25rem 0 0; font-size: .74rem; color: var(--text-dim); }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }
.fields button { justify-self: start; }
.error { color: var(--risk-critical); margin: 0; font-size: .78rem; }
@media (max-width: 650px) { .fields { grid-template-columns: 1fr; } .fields button { width: 100%; } }
</style>
