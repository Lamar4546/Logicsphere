<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps({
  shipments: { type: Array, default: () => [] },
  selectedId: { type: String, default: null },
})
const emit = defineEmits(['select'])

const mapElement = ref(null)
let map, layer, hasFitted = false

const hasValue = (v) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v))
const point = (lat, lng) => (hasValue(lat) && hasValue(lng) ? [Number(lat), Number(lng)] : null)
const isActive = (s) => !['delivered', 'cancelled'].includes(s.status)
const stateOf = (s) => (s.status === 'delayed' ? 'delayed' : s.status === 'at_risk' ? 'at_risk' : 'normal')

// Everything we can draw for one shipment, from best to weakest source:
// live position > road route > straight line between the two endpoints.
function geometry(s) {
  const coords = s.route_geometry?.coordinates
  const road = Array.isArray(coords) && coords.length > 1 ? coords.map(([lng, lat]) => [lat, lng]) : null
  const live = point(s.current_latitude, s.current_longitude)
  const origin = point(s.origin_latitude, s.origin_longitude)
  const destination = point(s.destination_latitude, s.destination_longitude)
  const line = road || (origin && destination ? [origin, destination] : null)
  return { live, road, line, origin, destination, anchor: live || origin || (road && road[0]) || null }
}

const items = computed(() => props.shipments.filter(isActive).map((s) => ({ s, g: geometry(s) })))
const plotted = computed(() => items.value.filter((i) => i.g.anchor))
const unplotted = computed(() => items.value.length - plotted.value.length)
const counts = computed(() => ({
  normal: items.value.filter((i) => stateOf(i.s) === 'normal').length,
  at_risk: items.value.filter((i) => stateOf(i.s) === 'at_risk').length,
  delayed: items.value.filter((i) => stateOf(i.s) === 'delayed').length,
}))

// Leaflet writes colors into SVG attributes, where var(--x) is not reliable,
// so read the resolved theme colors from the map element instead.
function palette() {
  const css = getComputedStyle(mapElement.value)
  const get = (name, fallback) => css.getPropertyValue(name).trim() || fallback
  return {
    normal: get('--signal', '#277fc8'),
    at_risk: get('--risk-high', '#d87535'),
    delayed: get('--risk-critical', '#cf4e5b'),
  }
}

function boundsOfAll() {
  const bounds = L.latLngBounds([])
  plotted.value.forEach(({ g }) => {
    if (g.line) g.line.forEach((p) => bounds.extend(p))
    if (g.anchor) bounds.extend(g.anchor)
  })
  return bounds
}

function fit() {
  const bounds = boundsOfAll()
  if (map && bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 10 })
}

function render() {
  if (!mapElement.value) return
  if (!map) {
    map = L.map(mapElement.value, { zoomControl: true }).setView([18.1, -77.3], 6)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors',
    }).addTo(map)
    layer = L.layerGroup().addTo(map)
  }
  layer.clearLayers()
  const colors = palette()

  // Pass 1: routes underneath. Pass 2: markers on top, so lines never cover them.
  plotted.value.forEach(({ s, g }) => {
    if (!g.line) return
    const selected = s.id === props.selectedId
    L.polyline(g.line, {
      color: colors[stateOf(s)],
      weight: selected ? 3 : 2,
      opacity: selected ? 0.9 : 0.45,
      dashArray: g.road ? null : '6 6', // dashed = straight line, no road route
    }).addTo(layer)
  })

  plotted.value.forEach(({ s, g }) => {
    const state = stateOf(s)
    const color = colors[state]
    const selected = s.id === props.selectedId
    if (g.destination) {
      L.circleMarker(g.destination, { radius: 4, color, weight: 1.5, fillColor: '#fff', fillOpacity: 1 }).addTo(layer)
    }
    const planned = !g.live // hollow marker = planned start, no live position yet
    L.circleMarker(g.anchor, {
      radius: selected ? 11 : state === 'normal' ? 7 : 9,
      color: planned ? color : '#fff',
      weight: selected ? 3 : 2,
      fillColor: color,
      fillOpacity: planned ? 0.25 : 1,
    })
      .bindTooltip(`${s.reference_number} · ${s.status}${planned ? ' · no live position yet' : ''}`)
      .on('click', () => emit('select', s))
      .addTo(layer)
  })

  // Fit once, so the 15s refresh never undoes the user's panning and zooming.
  if (!hasFitted && plotted.value.length) { fit(); hasFitted = true }
  nextTick(() => map.invalidateSize())
}

onMounted(render)
watch(() => [props.shipments, props.selectedId], render)
onBeforeUnmount(() => map?.remove())
</script>

<template>
  <section class="panel fleet">
    <div class="head">
      <div><span class="mono dim">LIVE FLEET</span><h2>All active shipments</h2></div>
      <div class="chips">
        <span class="chip normal">{{ counts.normal }} on track</span>
        <span class="chip at_risk">{{ counts.at_risk }} at risk</span>
        <span class="chip delayed">{{ counts.delayed }} delayed</span>
        <button class="ghost fit" type="button" @click="fit">Fit all</button>
      </div>
    </div>
    <div class="mapwrap">
      <div ref="mapElement" class="map" aria-label="Map of all active shipments"></div>
      <div v-if="!plotted.length" class="empty">
        <strong>Nothing to plot yet</strong>
        <span>Shipments appear here once they have a live position or a resolved route.</span>
      </div>
    </div>
    <p v-if="plotted.length && unplotted" class="note dim">
      {{ unplotted }} active shipment{{ unplotted === 1 ? ' has' : 's have' }} no location or route yet and
      {{ unplotted === 1 ? 'is' : 'are' }} not shown.
    </p>
    <p v-if="plotted.length" class="note dim">Solid dot: live position. Hollow dot: planned start. Dashed line: direct line, no road route.</p>
  </section>
</template>

<style scoped>
.fleet { padding: 1rem; margin: 1rem 0; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
.head .mono { font-size: .65rem; letter-spacing: .08em; }
.head h2 { font-size: 1rem; margin-top: .2rem; color: var(--text); }
.chips { display: flex; align-items: center; gap: .4rem; flex-wrap: wrap; }
.chip { font: .65rem var(--font-mono); padding: .25rem .5rem; border-radius: 999px; border: 1px solid var(--line); }
.chip.normal { color: var(--signal); border-color: var(--signal); }
.chip.at_risk { color: var(--risk-high); border-color: var(--risk-high); }
.chip.delayed { color: var(--risk-critical); border-color: var(--risk-critical); }
.fit { padding: .3rem .55rem; font-size: .7rem; }
.mapwrap { position: relative; margin-top: .85rem; border-radius: 7px; overflow: hidden; }
.map { height: 320px; background: var(--panel-2); }
.empty { position: absolute; inset: 0; z-index: 800; display: grid; place-content: center; gap: .35rem; text-align: center; padding: 1rem;
  background: color-mix(in srgb, var(--panel) 82%, transparent); color: var(--text); pointer-events: none; }
.empty span { color: var(--text-dim); font-size: .8rem; }
.note { margin: .6rem 0 0; font-size: .72rem; }
@media (max-width: 600px) { .map { height: 260px; } }
</style>