<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'

const props = defineProps({ shipments: { type: Array, default: () => [] }, selectedId: { type: String, default: null } })
const emit = defineEmits(['select'])
const container = ref(null)
const error = ref('')
let viewer
const lastPositions = new Map()
let lastFocusedId = null
const counts = computed(() => props.shipments.reduce((result, shipment) => {
  const type = typeOf(shipment)
  result[type] += 1
  return result
}, { plane: 0, ship: 0, truck: 0 }))

function typeOf(shipment) {
  const value = `${shipment.transport_mode || ''} ${shipment.mode || ''} ${shipment.shipment_type || ''} ${shipment.vehicle_type || ''}`.toLowerCase()
  if (/air|plane|flight|aircraft/.test(value)) return 'plane'
  if (/sea|ship|ocean|maritime|vessel/.test(value)) return 'ship'
  return 'truck'
}
function coordinates(shipment) {
  const has = (value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
  const latitude = Number(shipment.current_latitude)
  const longitude = Number(shipment.current_longitude)
  if (!has(shipment.current_latitude) || !has(shipment.current_longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
    const routePoint = shipment.route_geometry?.coordinates?.[0]
    if (Array.isArray(routePoint) && routePoint.length >= 2 && Number.isFinite(Number(routePoint[0])) && Number.isFinite(Number(routePoint[1]))) return [Number(routePoint[0]), Number(routePoint[1]), 0]
    const originLat = Number(shipment.origin_latitude)
    const originLng = Number(shipment.origin_longitude)
    return Number.isFinite(originLat) && Number.isFinite(originLng) ? [originLng, originLat, 0] : null
  }
  const point = [longitude, latitude, Number(shipment.current_altitude) || 0]
  if (typeOf(shipment) !== 'truck') return point
  const route = shipment.route_geometry?.coordinates
  if (!Array.isArray(route) || route.length < 2) return point
  let best = null
  let bestDistance = Infinity
  for (let i = 0; i < route.length - 1; i += 1) {
    const [ax, ay] = route[i], [bx, by] = route[i + 1]
    const dx = bx - ax, dy = by - ay
    const t = Math.max(0, Math.min(1, ((longitude - ax) * dx + (latitude - ay) * dy) / (dx * dx + dy * dy || 1)))
    const candidate = [ax + t * dx, ay + t * dy, 0]
    const distance = (candidate[0] - longitude) ** 2 + (candidate[1] - latitude) ** 2
    if (distance < bestDistance) { best = candidate; bestDistance = distance }
  }
  return best || point
}
function colorFor(shipment) {
  const styles = getComputedStyle(container.value)
  const token = shipment.status === 'delayed' ? '--risk-critical' : shipment.status === 'at_risk' ? '--risk-high' : '--signal'
  return Cesium.Color.fromCssColorString(styles.getPropertyValue(token).trim() || '#3b91df')
}
function iconFor(type) {
  return type === 'plane' ? '✈' : type === 'ship' ? '◆' : '●'
}
function markerSvg(type) {
  const paths = {
    plane: '<path d="M12 2 9 10 2 14v2l8-2v6l-2 2v1l4-1 4 1v-1l-2-2v-6l8 2v-2l-7-4-3-8z"/>',
    ship: '<path d="M3 13 5 5h14l2 8-9 7-9-7zm3-6-1 5h14l-1-5H6z"/>',
    truck: '<path d="M2 5h12v11H2zM14 9h4l4 4v3h-8zM6 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm12 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/>',
  }
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white">${paths[type]}</svg>`)}`
}
function render() {
  if (!viewer || viewer.isDestroyed()) return
  error.value = ''
  viewer.entities.removeAll()
  props.shipments.filter((shipment) => !['delivered', 'cancelled'].includes(shipment.status)).forEach((shipment) => {
    const point = coordinates(shipment)
    if (!point) return
    const type = typeOf(shipment)
    const color = colorFor(shipment)
    const heading = Number(shipment.current_heading ?? shipment.heading) || 0
    const target = Cesium.Cartesian3.fromDegrees(...point)
    let position = target
    const previous = lastPositions.get(shipment.id)
    if (previous && Cesium.Cartesian3.distance(previous, target) > 5) {
      const startedAt = Cesium.JulianDate.now()
      position = new Cesium.CallbackProperty((time, result) => {
        const elapsed = Math.max(0, Cesium.JulianDate.secondsDifference(time, startedAt))
        const fraction = Math.min(1, elapsed / 15)
        return Cesium.Cartesian3.lerp(previous, target, fraction, result || new Cesium.Cartesian3())
      }, false)
    }
    lastPositions.set(shipment.id, target)
    const route = shipment.route_geometry?.coordinates
    if (Array.isArray(route) && route.length > 1) {
      viewer.entities.add({ id: `route-${shipment.id}`, polyline: { positions: Cesium.Cartesian3.fromDegreesArray(route.flat()), width: 2, material: color.withAlpha(.58), clampToGround: type === 'truck' } })
    }
    viewer.entities.add({
      id: String(shipment.id), name: shipment.reference_number || 'Shipment', position,
      orientation: type === 'plane' ? new Cesium.CallbackProperty(() => Cesium.Transforms.headingPitchRollQuaternion(Cesium.Cartesian3.fromDegrees(...point), new Cesium.HeadingPitchRoll(Cesium.Math.toRadians(heading), 0, 0)), false) : undefined,
      billboard: { image: markerSvg(type), width: 24, height: 24, color, rotation: new Cesium.CallbackProperty(() => -Cesium.Math.toRadians(heading), false), alignedAxis: Cesium.Cartesian3.UNIT_Z, heightReference: type === 'truck' || type === 'ship' ? Cesium.HeightReference.CLAMP_TO_GROUND : Cesium.HeightReference.NONE },
      label: { text: `${iconFor(type)}  ${shipment.reference_number || 'Shipment'}`, font: '12px sans-serif', fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 3, style: Cesium.LabelStyle.FILL_AND_OUTLINE, pixelOffset: new Cesium.Cartesian2(0, -18), distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 3500000) },
      properties: { shipmentId: shipment.id, type, heading },
    })
  })
  const selected = props.shipments.find((shipment) => shipment.id === props.selectedId)
  const point = selected && coordinates(selected)
  if (point && selected.id !== lastFocusedId) {
    viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(...point, 1800000), duration: .6 })
    lastFocusedId = selected.id
  }
}
function focusAll() {
  if (!viewer || viewer.isDestroyed()) return
  const entities = viewer.entities.values.filter((entity) => entity.position)
  if (entities.length) viewer.flyTo(entities).catch((cause) => { error.value = cause.message || 'Unable to frame shipment locations.' })
}
function onClick(event) {
  const picked = viewer?.scene.pick(event.position)
  const id = picked?.id?.properties?.shipmentId?.getValue()
  const shipment = props.shipments.find((entry) => String(entry.id) === String(id))
  if (shipment) emit('select', shipment)
}
onMounted(() => {
  try {
    viewer = new Cesium.Viewer(container.value, {
      animation: false, timeline: false, baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, infoBox: false, selectionIndicator: false,
      // Viewer expects a concrete ImageryLayer (not the Promise returned by
      // ImageryLayer.fromProviderAsync). Add the OSM provider synchronously.
      baseLayer: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(), requestRenderMode: false,
    })
    viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({ url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', credit: '© OpenStreetMap contributors', maximumLevel: 19 }))
    viewer.clock.shouldAnimate = true
    viewer.scene.globe.enableLighting = true
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = 25000
    viewer.screenSpaceEventHandler.setInputAction(onClick, Cesium.ScreenSpaceEventType.LEFT_CLICK)
    render()
  } catch (cause) { error.value = cause.message || 'The 3D map could not be initialized.' }
})
watch(() => [props.shipments, props.selectedId], render, { deep: true })
onBeforeUnmount(() => { if (viewer && !viewer.isDestroyed()) viewer.destroy() })
</script>

<template>
  <section class="panel globe-panel">
    <header class="globe-head"><div><span class="mono dim">GOD’S EYE VIEW</span><h2>3D shipment tracking</h2></div><div class="legend"><span>✈ {{ counts.plane }} air</span><span>◆ {{ counts.ship }} sea</span><span>● {{ counts.truck }} road</span><button type="button" @click="focusAll">Fit all</button></div></header>
    <div class="globe-wrap"><div ref="container" class="globe"></div><p v-if="error" class="globe-error">{{ error }}</p><p v-else-if="!shipments.some((shipment) => coordinates(shipment))" class="globe-empty">Shipment positions appear here when your tracking providers send coordinates.</p></div>
    <p class="globe-note">Positions and headings use shipment telemetry. Configure aviation, AIS, and road GPS feeds to track each transport type live.</p>
  </section>
</template>

<style scoped>
.globe-panel{padding:1rem;margin:1rem 0}.globe-head{display:flex;justify-content:space-between;align-items:flex-start;gap:.75rem;flex-wrap:wrap}.globe-head .mono{font-size:.65rem;letter-spacing:.08em}.globe-head h2{font-size:1rem;margin-top:.2rem}.legend{display:flex;align-items:center;gap:.45rem;flex-wrap:wrap}.legend span{font-size:.68rem;color:var(--text-dim);padding:.25rem .45rem;border:1px solid var(--line);border-radius:99px}.legend button{padding:.3rem .55rem;font-size:.7rem}.globe-wrap{position:relative;margin-top:.8rem;overflow:hidden;border:1px solid var(--line);border-radius:8px}.globe{height:440px;background:#07182b}.globe-empty,.globe-error{position:absolute;inset:auto 1rem 1rem;margin:0;padding:.65rem .8rem;border-radius:8px;background:color-mix(in srgb,var(--panel) 90%,transparent);text-align:center;font-size:.78rem;color:var(--text-dim);pointer-events:none}.globe-note{margin:.55rem 0 0;color:var(--text-dim);font-size:.7rem;line-height:1.4}:deep(.cesium-viewer-bottom){font-size:10px}:deep(.cesium-widget-credits){background:rgba(5,15,24,.65)}@media(max-width:650px){.globe{height:320px}.globe-head{align-items:flex-start}.legend{gap:.3rem}.legend span{font-size:.62rem}}
</style>
