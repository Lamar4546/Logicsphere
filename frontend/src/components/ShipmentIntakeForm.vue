<script setup>
import { reactive, ref } from 'vue'
import { api } from '../services/api.js'

const emit = defineEmits(['created'])

const form = reactive({
  reference_number: '',
  origin: '',
  destination: '',
  eta_original: '',
  eta_current: '',
  last_event_description: '',
})
const submitting = ref(false)
const error = ref('')

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await api.createShipment({
      ...form,
      status: 'in_transit',
      source_system: 'manual_demo_entry',
    })
    Object.assign(form, {
      reference_number: '', origin: '', destination: '',
      eta_original: '', eta_current: '', last_event_description: '',
    })
    emit('created')
  } catch (err) {
    error.value = err.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="panel intake" @submit.prevent="submit">
    <p class="dim hint">
      Stands in for a TMS/carrier sync (SRS §10.2 step 1). Set a later "current ETA"
      than "original ETA" to simulate a delay worth evaluating.
    </p>
    <div class="row">
      <input v-model="form.reference_number" placeholder="Reference # (e.g. SHP-1042)" required />
      <input v-model="form.origin" placeholder="Origin" />
      <input v-model="form.destination" placeholder="Destination" />
    </div>
    <div class="row">
      <label class="field">
        <span class="mono dim">Original ETA</span>
        <input v-model="form.eta_original" type="datetime-local" />
      </label>
      <label class="field">
        <span class="mono dim">Current ETA</span>
        <input v-model="form.eta_current" type="datetime-local" />
      </label>
    </div>
    <input v-model="form.last_event_description" placeholder="Last tracking event (optional)" />
    <div class="row actions">
      <button type="submit" class="primary" :disabled="submitting">
        {{ submitting ? 'Adding…' : 'Add Shipment' }}
      </button>
      <span v-if="error" class="err">{{ error }}</span>
    </div>
  </form>
</template>

<style scoped>
.intake {
  padding: 1rem;
  margin-bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.hint {
  font-size: 0.78rem;
  margin: 0 0 0.25rem;
}
.row {
  display: flex;
  gap: 0.6rem;
}
.row input { flex: 1; }
.field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.7rem;
}
.actions {
  align-items: center;
  gap: 0.75rem;
}
.err {
  color: var(--risk-critical);
  font-size: 0.8rem;
}
</style>
