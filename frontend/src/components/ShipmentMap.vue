<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../services/api.js'

const props = defineProps({ shipment: { type: Object, required: true } })
const mapElement = ref(null)
const tileIssue = ref(false)
const routeLoading = ref(false)
const routeError = ref('')
const routeAttemptedFor = ref('')
let map, marker, routeLine, endpointLayer
const origin = computed(() => props.shipment.origin || 'Origin unavailable')
const destination = computed(() => props.shipment.destination || 'Destination unavailable')
const hasLocation = computed(() => [props.shipment.current_latitude, props.shipment.current_longitude].every((value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))))
const routeCoordinates = computed(() => {
  const coordinates = props.shipment.route_geometry?.coordinates
  return Array.isArray(coordinates) && coordinates.length > 1 ? coordinates.map(([longitude, latitude]) => [latitude, longitude]) : []
})
const hasRoute = computed(() => routeCoordinates.value.length > 1)
const coordinates = computed(() => {
  const lat = Number(props.shipment.current_latitude); const lng = Number(props.shipment.current_longitude)
  return hasLocation.value ? [lat, lng] : [20, 0]
})
const etaLabel = computed(() => props.shipment.eta_current ? new Date(props.shipment.eta_current).toLocaleString() : 'ETA awaiting carrier update')
const routeSummary = computed(() => {
  const distance = Number(props.shipment.route_distance_meters || 0)
  const duration = Number(props.shipment.route_duration_seconds || 0)
  if (!distance || !duration) return 'Route planning pending'
  const hours = Math.floor(duration / 3600); const minutes = Math.round((duration % 3600) / 60)
  return `${(distance / 1000).toFixed(1)} km · ${hours ? `${hours}h ` : ''}${minutes}m drive`
})
async function refreshRoute() {
  routeLoading.value = true; routeError.value = ''
  try {
    const shipment = await api.refreshShipmentRoute(props.shipment.id)
    Object.assign(props.shipment, shipment)
  } catch (error) { routeError.value = error.message || 'Route could not be planned.' } finally { routeLoading.value = false }
}
async function ensureRoute() {
  if (!props.shipment.origin || !props.shipment.destination || hasRoute.value || routeLoading.value || routeAttemptedFor.value === props.shipment.id) return
  routeAttemptedFor.value = props.shipment.id
  await refreshRoute()
}
function renderMap() {
  if (!mapElement.value) return
  if (!map) {
    map = L.map(mapElement.value, { zoomControl: true }).setView(coordinates.value, hasLocation.value ? 7 : 2)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' })
      .on('tileerror', () => { tileIssue.value = true })
      .addTo(map)
  }
  if (marker) marker.remove()
  if (routeLine) routeLine.remove()
  if (endpointLayer) endpointLayer.remove()
  if (hasRoute.value) {
    routeLine = L.polyline(routeCoordinates.value, { color: '#3194ff', weight: 4, opacity: .9 }).addTo(map)
    endpointLayer = L.layerGroup([
      L.circleMarker(routeCoordinates.value[0], { radius: 7, color: '#43c999', fillOpacity: 1 }).bindTooltip('Origin'),
      L.circleMarker(routeCoordinates.value.at(-1), { radius: 7, color: '#ef8838', fillOpacity: 1 }).bindTooltip('Destination'),
    ]).addTo(map)
    map.fitBounds(routeLine.getBounds(), { padding: [32, 32], maxZoom: 10 })
  }
  if (hasLocation.value) {
    marker = L.marker(coordinates.value, { icon: L.divIcon({ className: 'shipment-marker', html: '<span>⌁</span>', iconSize: [32, 32], iconAnchor: [16, 16] }) }).addTo(map).bindPopup(`<strong>${props.shipment.reference_number}</strong><br>ETA: ${etaLabel.value}`)
    if (!hasRoute.value) map.setView(coordinates.value, 8)
  } else if (!hasRoute.value) map.setView(coordinates.value, 2)
  nextTick(() => map.invalidateSize())
}
onMounted(() => { renderMap(); ensureRoute() })
watch(() => props.shipment, () => { renderMap(); ensureRoute() }, { deep: true })
onBeforeUnmount(() => map?.remove())
</script>

<template>
  <aside class="panel map-card">
    <div class="head"><div><span class="mono dim">{{ hasRoute ? 'ROUTE PLAN' : 'LIVE ROUTE' }}</span><h2>{{ shipment.reference_number }}</h2></div><span class="map-status" :class="{ live: hasLocation }">{{ hasLocation ? 'LIVE' : hasRoute ? 'PLANNED' : 'WAITING' }}</span></div>
    <div class="map-frame"><div ref="mapElement" class="map-wrap" aria-label="OpenStreetMap shipment route and live location"></div><div v-if="tileIssue" class="map-fallback">Map background is unavailable. The resolved route and live coordinate state remain available below.</div><div class="eta-overlay"><span>{{ hasRoute ? 'Planned route' : 'Current ETA' }}</span><strong>{{ hasRoute ? routeSummary : etaLabel }}</strong><small :class="{ live: hasLocation }">{{ hasLocation ? '● Live position received' : hasRoute ? '○ Route resolved — awaiting carrier position' : '○ Awaiting carrier position' }}</small></div></div>
    <div v-if="!hasLocation" class="map-note"><span>{{ hasRoute ? 'The route was calculated from the named locations. Connect a carrier or GPS feed to place the live marker on it.' : 'Add named locations to plan a route, or connect a carrier/GPS feed to show a live marker.' }}</span><button v-if="shipment.origin && shipment.destination && !hasRoute" type="button" :disabled="routeLoading" @click="refreshRoute">{{ routeLoading ? 'Planning…' : 'Plan route' }}</button></div><p v-if="routeError" class="route-error">{{ routeError }}</p>
    <dl><div><dt>Origin</dt><dd>{{ origin }}</dd></div><div><dt>Destination</dt><dd>{{ destination }}</dd></div><div><dt>Last tracking event</dt><dd>{{ shipment.last_event_description || 'No carrier event received yet.' }}</dd></div><div><dt>Current ETA</dt><dd>{{ shipment.eta_current ? new Date(shipment.eta_current).toLocaleString() : 'Not available' }}</dd></div></dl>
  </aside>
</template>

<style scoped>
.map-card{padding:1rem;margin:0;min-width:0}.head{display:flex;justify-content:space-between;gap:1rem;align-items:start}.head .mono{font-size:.65rem;letter-spacing:.08em}.head h2{font-size:1rem;margin-top:.2rem}.map-status{font:.62rem var(--font-mono);letter-spacing:.06em;color:var(--text-dim);padding:.28rem .42rem;border:1px solid var(--line);border-radius:999px}.map-status.live{color:var(--risk-low);border-color:var(--risk-low)}.map-frame{position:relative;margin:1rem 0}.map-wrap{height:340px;border-radius:7px;overflow:hidden;background:var(--panel-2)}.map-fallback{position:absolute;z-index:450;inset:0;display:grid;place-items:center;padding:2rem;text-align:center;background:color-mix(in srgb,var(--panel-2) 88%,transparent);color:var(--text);font-size:.8rem}.eta-overlay{position:absolute;z-index:500;right:.7rem;bottom:.7rem;max-width:calc(100% - 1.4rem);padding:.55rem .65rem;border:1px solid var(--line);border-radius:7px;background:color-mix(in srgb,var(--panel) 94%,transparent);box-shadow:0 5px 18px rgba(20,48,76,.14)}.eta-overlay span{display:block;color:var(--text-dim);font:.6rem var(--font-mono);text-transform:uppercase}.eta-overlay strong{display:block;margin-top:.15rem;font-size:.77rem}.eta-overlay small{display:block;margin-top:.2rem;color:var(--text-dim);font-size:.65rem}.eta-overlay small.live{color:var(--risk-low)}.map-note{display:flex;align-items:center;justify-content:space-between;gap:.75rem;color:var(--text-dim);font-size:.78rem;margin:-.45rem 0 .45rem}.map-note button{padding:.32rem .5rem;font-size:.7rem;white-space:nowrap}.route-error{margin:0 0 .75rem;color:var(--risk-critical);font-size:.75rem}dl{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin:0}dt{font:.65rem var(--font-mono);color:var(--text-dim);text-transform:uppercase}dd{margin:.2rem 0 0;font-size:.8rem}:deep(.shipment-marker){display:grid;place-items:center;border:2px solid #fff;border-radius:50%;background:var(--signal);color:#fff;box-shadow:0 3px 10px rgba(17,54,91,.35);font-weight:800}@media(max-width:600px){.map-wrap{height:290px}dl{grid-template-columns:1fr}.map-note{align-items:flex-start;flex-direction:column}}
</style>
