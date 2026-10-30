<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { getPublicTracking } from '../services/api.js'

// URL shape: /track/<token>
const token = decodeURIComponent(window.location.pathname.split('/')[2] || '')

const data = ref(null)
const error = ref('')
const loading = ref(true)
const mapElement = ref(null)
let map, routeLine, marker, timer

const hasValue = (v) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v))
const status = computed(() => data.value?.status)
const isDone = computed(() => ['delivered', 'cancelled'].includes(status.value))
const delayed = computed(() => ['delayed', 'at_risk'].includes(status.value))
const hasPosition = computed(() => hasValue(data.value?.current_latitude) && hasValue(data.value?.current_longitude))
const route = computed(() => {
  const coords = data.value?.route_geometry?.coordinates
  return Array.isArray(coords) && coords.length > 1 ? coords.map(([lng, lat]) => [lat, lng]) : []
})
const hasMap = computed(() => hasPosition.value || route.value.length > 1)

const etaText = computed(() => {
  const value = data.value?.eta_current
  if (!value) return ''
  const date = new Date(value)
  const sameDay = date.toDateString() === new Date().toDateString()
  return sameDay
    ? date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : date.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })
})

const headline = computed(() => {
  if (status.value === 'delivered') return 'Delivered'
  if (status.value === 'cancelled') return 'This shipment was cancelled'
  if (status.value === 'delayed') return etaText.value ? `Delayed, now expected by ${etaText.value}` : 'Your delivery is delayed'
  if (status.value === 'at_risk') return 'Your delivery may be delayed'
  return etaText.value ? `On the way, arriving by ${etaText.value}` : 'On the way'
})

const steps = computed(() => {
  const s = status.value
  const moving = ['in_transit', 'at_risk', 'delayed', 'delivered'].includes(s)
  return [
    { label: 'Delivered', detail: s === 'delivered' ? 'Package delivered' : etaText.value ? `Expected ${etaText.value}` : 'Awaiting delivery', state: s === 'delivered' ? 'done' : 'upcoming' },
    { label: 'In transit', detail: data.value?.last_event_description || 'On its way to you', state: s === 'delivered' ? 'done' : moving ? 'current' : 'upcoming' },
    { label: 'Order placed', detail: 'We received your order', state: 'done' },
  ]
})

function stop() { window.clearInterval(timer); timer = null }

async function load() {
  try {
    data.value = await getPublicTracking(token)
    error.value = ''
    if (isDone.value) stop()
  } catch (err) {
    // keep showing the last good data if a refresh fails
    if (!data.value) { error.value = err.message; stop() }
  } finally {
    loading.value = false
  }
}

function colors() {
  const css = getComputedStyle(mapElement.value)
  const get = (name, fallback) => css.getPropertyValue(name).trim() || fallback
  return { signal: get('--signal', '#277fc8'), low: get('--risk-low', '#279a6d'), high: get('--risk-high', '#d87535') }
}

function renderMap() {
  if (!mapElement.value || !hasMap.value) return
  const c = colors()
  if (!map) {
    map = L.map(mapElement.value, { zoomControl: false, attributionControl: true })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map)
  }
  routeLine?.remove()
  marker?.remove()
  const bounds = []
  if (route.value.length > 1) {
    routeLine = L.polyline(route.value, { color: c.signal, weight: 4, opacity: .85 }).addTo(map)
    bounds.push(...route.value)
  }
  if (hasPosition.value) {
    const here = [Number(data.value.current_latitude), Number(data.value.current_longitude)]
    marker = L.circleMarker(here, { radius: 9, color: '#fff', weight: 3, fillColor: delayed.value ? c.high : c.signal, fillOpacity: 1 }).addTo(map)
    bounds.push(here)
  }
  nextTick(() => { map.invalidateSize(); if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 }) })
}

watch(data, () => nextTick(renderMap))

onMounted(async () => {
  document.title = 'Track your shipment · LogiSphere'
  await load()
  if (!error.value && !isDone.value) timer = window.setInterval(load, 15000)
})
onBeforeUnmount(() => { stop(); map?.remove() })
</script>

<template>
  <main class="track">
    <header class="top"><strong class="display">LogiSphere</strong><span class="mono dim">SHIPMENT TRACKING</span></header>

    <p v-if="loading" class="dim">Loading your shipment…</p>

    <section v-else-if="error" class="panel state">
      <h1>We couldn't open this link</h1>
      <p class="dim">{{ error }}</p>
      <button type="button" @click="loading = true; error = ''; load()">Try again</button>
    </section>

    <template v-else-if="data">
      <span class="mono eyebrow">SHIPMENT STATUS</span>
      <h1>{{ headline }}</h1>

      <section class="panel mapcard" v-show="hasMap">
        <div ref="mapElement" class="map" aria-label="Map showing your shipment"></div>
        <div class="meta" v-if="data.driver_first_name || data.vehicle_label">
          <div v-if="data.driver_first_name"><span class="mono dim">DRIVER</span><strong>{{ data.driver_first_name }}</strong></div>
          <div v-if="data.vehicle_label"><span class="mono dim">VEHICLE</span><strong>{{ data.vehicle_label }}</strong></div>
        </div>
      </section>
      <p v-if="!hasMap" class="panel nomap dim">Live location will appear here once the carrier shares it.</p>

      <h2 class="mono dim hist">TRACKING HISTORY</h2>
      <ol class="steps">
        <li v-for="s in steps" :key="s.label" :class="s.state">
          <span class="node">{{ s.state === 'done' ? '✓' : '' }}</span>
          <strong>{{ s.label }}</strong><small class="dim">{{ s.detail }}</small>
        </li>
      </ol>

      <aside v-if="data.notice" class="notice">
        <strong>{{ delayed ? 'Delivery update' : 'Update' }}</strong>
        <p>{{ data.notice }}</p>
      </aside>

      <footer class="mono dim">Shipment ID: {{ data.reference_number }}</footer>
    </template>
  </main>
</template>

<style scoped>
.track { max-width: 440px; margin: 0 auto; padding: 1.25rem 1.25rem 2.5rem; min-height: 100dvh; }
.top { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1.25rem; border-bottom: 1px solid var(--line); }
.top .mono { font-size: .65rem; letter-spacing: .08em; }
.eyebrow { color: var(--signal); font-size: .68rem; letter-spacing: .08em; }
h1 { font-size: 1.6rem; line-height: 1.2; margin: .4rem 0 1.1rem; }
.mapcard { overflow: hidden; padding: 0; }
.map { height: 210px; background: var(--panel-2); }
.meta { display: flex; justify-content: space-between; padding: .9rem 1rem; }
.meta span { display: block; font-size: .62rem; margin-bottom: .15rem; }
.nomap { padding: 1rem; font-size: .85rem; }
.hist { font-size: .68rem; letter-spacing: .08em; margin: 1.6rem 0 .9rem; }
.steps { list-style: none; margin: 0; padding: 0; }
.steps li { position: relative; display: grid; padding: 0 0 1.4rem 2.2rem; }
.steps li::before { content: ''; position: absolute; left: .7rem; top: 1.5rem; bottom: 0; width: 2px; background: var(--line); }
.steps li:last-child { padding-bottom: 0; } .steps li:last-child::before { display: none; }
.steps small { font-size: .78rem; margin-top: .1rem; }
.node { position: absolute; left: 0; top: 0; width: 1.5rem; height: 1.5rem; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); display: grid; place-items: center; font-size: .75rem; color: #fff; }
.done .node { background: var(--signal); border-color: var(--signal); }
.current .node { border-color: var(--signal); box-shadow: inset 0 0 0 4px var(--panel), inset 0 0 0 12px var(--signal); }
.upcoming strong, .upcoming small { opacity: .55; }
.notice { margin-top: 1.4rem; padding: .9rem 1rem; border-radius: 12px; background: color-mix(in srgb, var(--signal) 12%, transparent); }
.notice p { margin: .4rem 0 0; font-size: .85rem; line-height: 1.5; color: var(--text-dim); }
footer { text-align: center; font-size: .68rem; margin-top: 2rem; }
.state { padding: 1.25rem; } .state h1 { font-size: 1.15rem; margin: 0 0 .5rem; } .state button { margin-top: .75rem; }
</style>