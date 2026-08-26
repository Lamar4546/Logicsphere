<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps({ shipment: { type: Object, required: true } })
const mapElement = ref(null)
const tileIssue = ref(false)
let map, marker
const origin = computed(() => props.shipment.origin || 'Origin unavailable')
const destination = computed(() => props.shipment.destination || 'Destination unavailable')
const hasLocation = computed(() => [props.shipment.current_latitude, props.shipment.current_longitude].every((value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))))
const coordinates = computed(() => {
  const lat = Number(props.shipment.current_latitude); const lng = Number(props.shipment.current_longitude)
  return hasLocation.value ? [lat, lng] : [20, 0]
})
const etaLabel = computed(() => props.shipment.eta_current ? new Date(props.shipment.eta_current).toLocaleString() : 'ETA awaiting carrier update')
function renderMap() {
  if (!mapElement.value) return
  if (!map) {
    map = L.map(mapElement.value, { zoomControl: true }).setView(coordinates.value, hasLocation.value ? 7 : 2)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' })
      .on('tileerror', () => { tileIssue.value = true })
      .addTo(map)
  }
  if (marker) marker.remove()
  if (hasLocation.value) {
    marker = L.marker(coordinates.value, { icon: L.divIcon({ className: 'shipment-marker', html: '<span>⌁</span>', iconSize: [32, 32], iconAnchor: [16, 16] }) }).addTo(map).bindPopup(`<strong>${props.shipment.reference_number}</strong><br>ETA: ${etaLabel.value}`)
    map.setView(coordinates.value, 8)
  } else map.setView(coordinates.value, 2)
  nextTick(() => map.invalidateSize())
}
onMounted(renderMap)
watch(() => props.shipment, renderMap, { deep: true })
onBeforeUnmount(() => map?.remove())
</script>

<template>
  <aside class="panel map-card">
    <div class="head"><div><span class="mono dim">LIVE ROUTE</span><h2>{{ shipment.reference_number }}</h2></div><span class="map-status" :class="{ live: hasLocation }">{{ hasLocation ? 'LIVE' : 'WAITING' }}</span></div>
    <div class="map-frame"><div ref="mapElement" class="map-wrap" aria-label="OpenStreetMap live shipment location"></div><div v-if="tileIssue" class="map-fallback">Map background is unavailable. The route details and live coordinate state remain available below.</div><div class="eta-overlay"><span>Current ETA</span><strong>{{ etaLabel }}</strong><small :class="{ live: hasLocation }">{{ hasLocation ? '● Live position received' : '○ Awaiting carrier position' }}</small></div></div>
    <p v-if="!hasLocation" class="map-note">Add latitude and longitude when creating a shipment, or connect a carrier/GPS feed to show a live marker.</p>
    <dl><div><dt>Origin</dt><dd>{{ origin }}</dd></div><div><dt>Destination</dt><dd>{{ destination }}</dd></div><div><dt>Last tracking event</dt><dd>{{ shipment.last_event_description || 'No carrier event received yet.' }}</dd></div><div><dt>Current ETA</dt><dd>{{ shipment.eta_current ? new Date(shipment.eta_current).toLocaleString() : 'Not available' }}</dd></div></dl>
  </aside>
</template>

<style scoped>
.map-card{padding:1rem;margin:0;min-width:0}.head{display:flex;justify-content:space-between;gap:1rem;align-items:start}.head .mono{font-size:.65rem;letter-spacing:.08em}.head h2{font-size:1rem;margin-top:.2rem}.map-status{font:.62rem var(--font-mono);letter-spacing:.06em;color:var(--text-dim);padding:.28rem .42rem;border:1px solid var(--line);border-radius:999px}.map-status.live{color:var(--risk-low);border-color:var(--risk-low)}.map-frame{position:relative;margin:1rem 0}.map-wrap{height:340px;border-radius:7px;overflow:hidden;background:var(--panel-2)}.map-fallback{position:absolute;z-index:450;inset:0;display:grid;place-items:center;padding:2rem;text-align:center;background:color-mix(in srgb,var(--panel-2) 88%,transparent);color:var(--text);font-size:.8rem}.eta-overlay{position:absolute;z-index:500;right:.7rem;bottom:.7rem;max-width:calc(100% - 1.4rem);padding:.55rem .65rem;border:1px solid var(--line);border-radius:7px;background:color-mix(in srgb,var(--panel) 94%,transparent);box-shadow:0 5px 18px rgba(20,48,76,.14)}.eta-overlay span{display:block;color:var(--text-dim);font:.6rem var(--font-mono);text-transform:uppercase}.eta-overlay strong{display:block;margin-top:.15rem;font-size:.77rem}.eta-overlay small{display:block;margin-top:.2rem;color:var(--text-dim);font-size:.65rem}.eta-overlay small.live{color:var(--risk-low)}.map-note{color:var(--text-dim);font-size:.78rem;margin:-.45rem 0 1rem}dl{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin:0}dt{font:.65rem var(--font-mono);color:var(--text-dim);text-transform:uppercase}dd{margin:.2rem 0 0;font-size:.8rem}:deep(.shipment-marker){display:grid;place-items:center;border:2px solid #fff;border-radius:50%;background:var(--signal);color:#fff;box-shadow:0 3px 10px rgba(17,54,91,.35);font-weight:800}@media(max-width:600px){.map-wrap{height:290px}dl{grid-template-columns:1fr}}
</style>
