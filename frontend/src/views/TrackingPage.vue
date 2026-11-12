<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { getPublicTracking } from '../services/api.js'
import PageSkeleton from '../components/PageSkeleton.vue'

const token = decodeURIComponent(window.location.pathname.split('/')[2] || '')
const data = ref(null)
const error = ref('')
const loading = ref(true)
const mapElement = ref(null)
let map, routeLine, marker, destinationMarker, timer, fitted = false

const hasValue = (v) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v))
const status = computed(() => data.value?.status || 'planned')
const isDone = computed(() => ['delivered', 'cancelled'].includes(status.value))
const delayed = computed(() => ['delayed', 'at_risk', 'exception'].includes(status.value))
const hasPosition = computed(() => hasValue(data.value?.current_latitude) && hasValue(data.value?.current_longitude))
const route = computed(() => {
  const coords = data.value?.route_geometry?.coordinates
  if (Array.isArray(coords) && coords.length > 1) return coords.map(([lng, lat]) => [lat, lng])
  if (hasPosition.value && hasValue(data.value?.destination_latitude) && hasValue(data.value?.destination_longitude)) {
    return [[Number(data.value.current_latitude), Number(data.value.current_longitude)], [Number(data.value.destination_latitude), Number(data.value.destination_longitude)]]
  }
  return []
})
const hasDestination = computed(() => hasValue(data.value?.destination_latitude) && hasValue(data.value?.destination_longitude))
const hasMap = computed(() => hasPosition.value || hasDestination.value || route.value.length > 1)
const events = computed(() => (Array.isArray(data.value?.tracking_events) ? data.value.tracking_events : [])
  .filter((event) => event?.description || event?.location)
  .sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0)))

function formatDate(value, options = { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) {
  if (!value) return ''
  const dateOnly = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  const date = dateOnly ? new Date(`${value}T12:00:00`) : new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString([], options)
}

const etaValue = computed(() => data.value?.ai_eta_at || data.value?.carrier_eta_at || data.value?.ai_eta_date || data.value?.carrier_eta_date || data.value?.eta_current)
const etaText = computed(() => formatDate(etaValue.value, etaValue.value?.length === 10
  ? { weekday: 'long', month: 'long', day: 'numeric' }
  : { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))
const headline = computed(() => {
  if (status.value === 'delivered') return 'Your package has been delivered'
  if (status.value === 'cancelled') return 'This shipment was cancelled'
  if (status.value === 'delayed') return 'Your delivery is running late'
  if (status.value === 'at_risk' || status.value === 'exception') return 'There’s an update on your delivery'
  if (status.value === 'in_transit') return 'Your package is on the way'
  return 'Tracking is getting started'
})
const displayStatus = computed(() => {
  const provider = data.value?.tracking_status
  return provider ? String(provider).replace(/([a-z])([A-Z])/g, '$1 $2') : String(status.value).replaceAll('_', ' ')
})
const etaSource = computed(() => {
  if (data.value?.ai_eta_source === 'aftership_ai') return 'AI delivery estimate'
  if (data.value?.ai_eta_source === '17track_estimate') return 'Tracking service estimate'
  if (data.value?.carrier_eta_at || data.value?.carrier_eta_date) return 'Carrier estimate'
  return 'Estimated arrival'
})
const modeLabel = computed(() => ({ truck: 'Land', ship: 'Sea', plane: 'Air' }[data.value?.transport_mode] || ({ road: 'Land', ocean: 'Sea', air: 'Air' }[data.value?.mode] || 'Shipment')))
const liveSourceLabel = computed(() => ({ traccar: 'Traccar GPS', aisstream: 'AIS vessel feed', opensky: 'OpenSky aircraft feed' }[data.value?.live_tracking_provider] || 'Carrier tracking'))

function stop() { window.clearInterval(timer); timer = null }
async function load() {
  try {
    data.value = await getPublicTracking(token)
    error.value = ''
    if (isDone.value) stop()
  } catch (err) {
    if (!data.value) { error.value = err.message; stop() }
  } finally { loading.value = false }
}

function renderMap() {
  if (!mapElement.value || !hasMap.value) return
  if (!map) {
    map = L.map(mapElement.value, { zoomControl: true, attributionControl: true })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map)
  }
  routeLine?.remove(); marker?.remove(); destinationMarker?.remove()
  const bounds = []
  if (route.value.length > 1) {
    routeLine = L.polyline(route.value, { color: '#297bc1', weight: 4, opacity: .7 }).addTo(map)
    bounds.push(...route.value)
  }
  if (hasPosition.value) {
    const here = [Number(data.value.current_latitude), Number(data.value.current_longitude)]
    marker = L.circleMarker(here, { radius: 9, color: '#fff', weight: 3, fillColor: delayed.value ? '#d87535' : '#277fc8', fillOpacity: 1 }).addTo(map)
    marker.bindTooltip('Latest reported location')
    bounds.push(here)
  }
  if (hasDestination.value) {
    const destination = [Number(data.value.destination_latitude), Number(data.value.destination_longitude)]
    destinationMarker = L.circleMarker(destination, { radius: 7, color: '#fff', weight: 2, fillColor: '#279a6d', fillOpacity: 1 }).addTo(map)
    destinationMarker.bindTooltip('Destination')
    bounds.push(destination)
  }
  nextTick(() => {
    map.invalidateSize()
    if (bounds.length && !fitted) { map.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 }); fitted = true }
  })
}
watch(data, () => nextTick(renderMap))
onMounted(async () => {
  document.title = 'Track your package · LogiSphere'
  await load()
  if (!error.value && !isDone.value) timer = window.setInterval(load, 30000)
})
onBeforeUnmount(() => { stop(); map?.remove() })
</script>

<template>
  <main class="track">
    <header class="top"><strong class="display">LogiSphere</strong><span class="mono dim">PACKAGE TRACKING</span></header>
    <PageSkeleton v-if="loading" variant="tracking" />
    <section v-else-if="error" class="panel state">
      <h1>We couldn’t open this tracking link</h1><p class="dim">{{ error }}</p>
      <button type="button" @click="loading = true; error = ''; load()">Try again</button>
    </section>
    <template v-else-if="data">
      <div class="intro">
        <span class="mono eyebrow">SHIPMENT {{ data.reference_number }}</span>
        <h1>{{ headline }}</h1>
        <p class="dim">{{ data.last_event_description || 'We’ll show new carrier updates here as they arrive.' }}</p>
      </div>

      <section class="summary panel">
        <div class="summary-status"><span class="pulse" :class="{ orange: delayed, green: isDone }"></span><div><span class="mono dim">CURRENT STATUS</span><strong>{{ displayStatus }}</strong></div></div>
        <div v-if="etaText" class="eta"><span class="mono dim">{{ etaSource }}</span><strong>{{ etaText }}</strong></div>
        <div v-if="data.tracking_carrier" class="carrier"><span class="mono dim">CARRIER</span><strong>{{ data.tracking_carrier }}</strong></div>
        <div class="carrier"><span class="mono dim">DELIVERY MODE</span><strong>{{ modeLabel }}</strong></div>
      </section>

      <section v-if="hasMap" class="panel mapcard">
        <div ref="mapElement" class="map" role="img" aria-label="Map showing the package route and latest reported position"></div>
        <p class="map-note" v-if="data.live_tracking_updated_at">Position from {{ liveSourceLabel }} · updated {{ formatDate(data.live_tracking_updated_at) }}. A straight line to the destination is approximate.</p>
        <p class="map-note" v-else>Carrier scans can be delayed. The marker shows the latest reported carrier location; a straight line to the destination is approximate.</p>
      </section>
      <section v-else class="panel nomap"><strong>Map location not available yet</strong><p class="dim">Carriers usually share a location after the first package scan. Check back as tracking updates arrive.</p></section>

      <section class="history">
        <div class="section-head"><h2 class="mono">DELIVERY UPDATES</h2><span class="mono dim" v-if="data.carrier_tracking_updated_at">Carrier data updated {{ formatDate(data.carrier_tracking_updated_at, { hour: 'numeric', minute: '2-digit' }) }}</span></div>
        <ol v-if="events.length" class="events">
          <li v-for="(event, index) in events" :key="`${event.time}-${index}`" :class="{ latest: index === 0 }">
            <span class="event-dot"></span><div class="event-copy"><strong>{{ event.description || event.status || 'Shipment update' }}</strong>
              <span v-if="event.location" class="dim">{{ event.location }}</span>
              <time class="mono dim">{{ formatDate(event.time) || 'Time unavailable' }}</time>
            </div>
          </li>
        </ol>
        <p v-else class="panel no-events dim">Carrier scans will appear here when they become available.</p>
      </section>
      <footer class="mono dim">Shared tracking · {{ data.reference_number }}</footer>
    </template>
  </main>
</template>

<style scoped>
.track { max-width: 760px; margin: 0 auto; padding: 1.25rem 1.25rem 3rem; min-height: 100dvh; }
.top { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1.7rem; border-bottom: 1px solid var(--line); }
.top .mono { font-size: .65rem; letter-spacing: .08em; }
.intro { margin-bottom: 1.2rem; }.eyebrow { color: var(--signal); font-size: .67rem; letter-spacing: .08em; }
h1 { font-size: clamp(1.45rem, 5vw, 2rem); line-height: 1.2; margin: .45rem 0 .4rem; }
.intro p { margin: 0; font-size: .9rem; line-height: 1.5; }
.summary { display: flex; flex-wrap: wrap; gap: 1.1rem 2rem; align-items: center; padding: 1rem 1.15rem; margin-bottom: 1rem; }
.summary-status { display: flex; align-items: center; gap: .7rem; flex: 1 1 180px; }.summary-status div, .eta, .carrier { display: grid; gap: .2rem; }
.summary .mono { font-size: .61rem; letter-spacing: .07em; }.summary strong { font-size: .92rem; text-transform: capitalize; }
.pulse { width: .65rem; height: .65rem; border-radius: 50%; background: var(--signal); box-shadow: 0 0 0 5px color-mix(in srgb, var(--signal) 13%, transparent); }
.pulse.orange { background: var(--risk-high); box-shadow: 0 0 0 5px color-mix(in srgb, var(--risk-high) 13%, transparent); }.pulse.green { background: var(--risk-low); box-shadow: 0 0 0 5px color-mix(in srgb, var(--risk-low) 13%, transparent); }
.mapcard { overflow: hidden; padding: 0; margin-bottom: 1.5rem; }.map { height: min(46vh, 360px); min-height: 250px; background: var(--panel-2); }.map-note { margin: 0; padding: .7rem 1rem; color: var(--text-dim); font-size: .72rem; }
.nomap { padding: 1.2rem; margin-bottom: 1.5rem; }.nomap p { font-size: .82rem; line-height: 1.5; margin: .35rem 0 0; }
.section-head { display: flex; justify-content: space-between; gap: .8rem; align-items: center; margin: 1.5rem 0 .9rem; }.section-head h2 { margin: 0; font-size: .67rem; letter-spacing: .08em; }.section-head span { font-size: .63rem; }
.events { list-style: none; margin: 0; padding: 0; }.events li { position: relative; display: flex; gap: .85rem; padding-bottom: 1.15rem; }.events li:not(:last-child)::before { content: ''; position: absolute; left: .31rem; top: .8rem; bottom: 0; width: 1px; background: var(--line); }
.event-dot { z-index: 1; flex: 0 0 .65rem; height: .65rem; margin-top: .2rem; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); }.latest .event-dot { border-color: var(--signal); background: var(--signal); }
.event-copy { display: grid; gap: .2rem; font-size: .86rem; }.event-copy .dim { font-size: .76rem; }.event-copy time { font-size: .64rem; margin-top: .1rem; }
.no-events { padding: 1rem; font-size: .8rem; }footer { text-align: center; font-size: .65rem; margin-top: 2rem; }.state { padding: 1.25rem; }.state h1 { font-size: 1.2rem; }.state button { margin-top: .75rem; }
@media (max-width: 540px) { .track { padding: 1rem 1rem 2rem; }.summary { gap: .9rem; }.carrier { flex-basis: 100%; }.section-head { align-items: flex-start; flex-direction: column; gap: .3rem; } }
</style>
