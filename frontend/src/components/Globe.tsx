import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  BoundingSphere, Cartesian2, Cartesian3, Cartographic, Color, ConstantProperty, Credit, CustomHeightmapTerrainProvider,
  DistanceDisplayCondition, EllipsoidTerrainProvider, GeographicTilingScheme, HeadingPitchRange,
  ClassificationType, HorizontalOrigin, ImageMaterialProperty, Math as CesiumMath, PinBuilder,
  PolygonHierarchy, PolylineDashMaterialProperty,
  Rectangle, ScreenSpaceEventType, UrlTemplateImageryProvider, VerticalOrigin,
  type ImageryLayer, type Viewer as CesiumViewer,
} from 'cesium'
import {
  Viewer, Entity, PolygonGraphics, PolylineGraphics, PointGraphics, BillboardGraphics, LabelGraphics,
  RectangleGraphics, ScreenSpaceEventHandler, ScreenSpaceEvent, type CesiumComponentRef,
} from 'resium'
import {
  CURIOSITY_RAW_IMAGES, MARS_TREK_URL, fetchTerrainTile, getLookup, inGeoref, layerUrl, orthoTileTemplate,
  type CuriosityWaypoint, type GeologicUnitProps, type LonLat, type ScienceCard,
} from '../api/cosmic'
import { GALE, MARS, MARS_RADIUS, featureUrl, type MarsFeature } from '../mars'
import { LANDING_SITES, type LandingSite } from '../data/landingSites'
import { useLayerStore } from '../store/layerStore'
import { useRouteStore } from '../store/routeStore'
import { SITE_MAX_HEIGHT, useMarsLabels, type Reserved, type SiteLabel } from './MarsLabels'
import { useMineralPoints, type MineralPick } from './MineralPoints'
import Inspector from './Inspector'
import { fitToVisible, measureMapFrame, visibleTangents } from '../mapFrame'

// Terrain: flat until the backend reports 3D height tiles (no Cesium ion, no token).
const flatTerrain = new EllipsoidTerrainProvider({ ellipsoid: MARS })

/** Real Mars heights from the backend: 5 m HiRISE/USGS grid in the routing area, MOLA elsewhere. */
function marsTerrain(datasetId: string, size: number) {
  return new CustomHeightmapTerrainProvider({
    width: size,
    height: size,
    ellipsoid: MARS,
    tilingScheme: new GeographicTilingScheme({ ellipsoid: MARS }),
    credit: new Credit('Mars terrain: HiRISE DTMs (NASA/JPL/UArizona), USGS MSL Gale DEM, MOLA (NASA GSFC/USGS)'),
    callback: (x, y, level) =>
      fetchTerrainTile(datasetId, level, x, y).then(b => new Float32Array(b)),
  })
}

// Global Mars colour basemap: Viking MDIM 2.1 colour mosaic (232 m/px) from NASA Mars Trek
// WMTS tiles (free, no token). Planetocentric, east-positive, 2×1 tiles at level 0 starting
// at −180° — the same convention as everything else (see src/mars.ts). Needs internet;
// offline the globe falls back to its plain base colour and the backend layers still work.
const marsBasemap = new UrlTemplateImageryProvider({
  url: 'https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg',
  tilingScheme: new GeographicTilingScheme({ ellipsoid: MARS }),
  maximumLevel: 7,
  credit: new Credit('Mars basemap: NASA/JPL/USGS Viking MDIM 2.1 colour mosaic via NASA Mars Trek · Place names: IAU/USGS Gazetteer of Planetary Nomenclature'),
})

// "Whole Mars" view: MOLA colour-shaded relief (463 m/px; blue = low, red/white = high) from
// NASA Mars Trek, same tiling as the basemap. Shown only in that view, above the basemap.
const molaRelief = new UrlTemplateImageryProvider({
  url: 'https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg',
  tilingScheme: new GeographicTilingScheme({ ellipsoid: MARS }),
  maximumLevel: 7,
  credit: new Credit('Whole Mars relief: MGS MOLA colour shaded relief 463 m (NASA/JPL/GSFC) via NASA Mars Trek'),
})
// Whole Mars view: straight down at Gale's longitude, 12°N, just far enough for the whole disc
// to fit the UNCOVERED map area (src/mapFrame.ts) with a 10 % margin.
function wholeMarsCamera(v: CesiumViewer) {
  const { tx, ty } = visibleTangents(v)
  const fit = 0.9 * Math.min(tx, ty)
  // tan(disc half-angle) = R / sqrt(D² − R²) must stay within the uncovered area.
  const dist = MARS_RADIUS * Math.sqrt(1 + 1 / (fit * fit))
  return { destination: Cartesian3.fromDegrees(GALE.lon, 12, dist - MARS_RADIUS, MARS) }
}
const LANDING_ICON = (() => {
  // Landing-site symbol: teal ring with a white centre.
  const c = document.createElement('canvas')
  c.width = c.height = 28
  const g = c.getContext('2d')!
  g.shadowColor = 'rgba(0,0,0,0.8)'
  g.shadowBlur = 4
  g.fillStyle = '#2dd4bf'
  g.beginPath(); g.arc(14, 14, 8, 0, Math.PI * 2); g.fill()
  g.shadowBlur = 0
  g.strokeStyle = '#0a0e1a'
  g.lineWidth = 2
  g.stroke()
  g.fillStyle = '#ffffff'
  g.beginPath(); g.arc(14, 14, 3, 0, Math.PI * 2); g.fill()
  return c.toDataURL()
})()
const LANDING_TEAL = Color.fromCssColorString('#5eead4')
const LANDING_LABEL_OFFSET = new Cartesian2(14, 0)

// Initial camera: lon, lat, altitude (m) — over Gale Crater, 50 km up.
const START_VIEW = [137.4, -4.6, 50_000] as const
// "Go to Gale Crater": centred on the IAU crater centre, high enough to frame the 154 km crater.
const GALE_RECT = (() => {
  // The whole 154 km crater plus a 15 % margin, as a lon/lat box (framed by fitToVisible).
  const halfLat = CesiumMath.toDegrees((GALE.d * 1000 / 2) * 1.15 / MARS_RADIUS)
  const halfLon = halfLat / Math.cos(CesiumMath.toRadians(GALE.lat))
  return Rectangle.fromDegrees(GALE.lon - halfLon, GALE.lat - halfLat, GALE.lon + halfLon, GALE.lat + halfLat)
})()

const pins = new PinBuilder()
// Theme: blue = start (A), pink = destination (B) / terrain-safe route, red dashed = shortest route, purple = science sites.
const START_PIN = pins.fromText('A', Color.fromCssColorString('#4a9eff'), 40).toDataURL()
const END_PIN = pins.fromText('B', Color.fromCssColorString('#ff4d8d'), 40).toDataURL()
const SITE_PIN = pins.fromColor(Color.fromCssColorString('#7c3aed'), 30).toDataURL()
const GALE_ICON = (() => {
  // Crater symbol: glowing ring with a centre dot.
  const c = document.createElement('canvas')
  c.width = c.height = 40
  const g = c.getContext('2d')!
  g.shadowColor = 'rgba(255,77,141,0.9)'
  g.shadowBlur = 8
  g.strokeStyle = '#ff4d8d'
  g.lineWidth = 3
  g.beginPath(); g.arc(20, 20, 12, 0, Math.PI * 2); g.stroke()
  g.fillStyle = '#e8f0ff'
  g.beginPath(); g.arc(20, 20, 3, 0, Math.PI * 2); g.fill()
  return c.toDataURL()
})()

// Both routes are drawn together: terrain-safe = solid pink, shortest = dashed red.
const ROUTE_STYLE = {
  terrain: { color: Color.fromCssColorString('#ff4d8d'), width: 5 },
  shortest: { color: Color.fromCssColorString('#ff3b30'), width: 4 },
} as const
const FOOTPRINT_COLOR = Color.fromCssColorString('#4a9eff')
const INK = Color.fromCssColorString('#e8f0ff')
const HALO = Color.fromCssColorString('#0a0e1a')
// Pins ignore depth only when close (so a 1–4 m overlay never hides them) but are still
// hidden behind the planet at globe scale.
const NEAR_NO_DEPTH = 400_000
// Site and A/B pins are local detail: hidden when zoomed out (the Gale marker stands in).
const LOCAL_ONLY = new DistanceDisplayCondition(0, SITE_MAX_HEIGHT)
// Constant Cesium objects (inline `new …` in JSX would be re-applied on every render).
const FOOTPRINT_LABEL_OFFSET = new Cartesian2(0, -4)
const FOOTPRINT_LABEL_DDC = new DistanceDisplayCondition(0, 250_000)
const GALE_LABEL_OFFSET = new Cartesian2(0, 18)
const ROUTE_DIM = { terrain: ROUTE_STYLE.terrain.color.withAlpha(0.85), shortest: ROUTE_STYLE.shortest.color.withAlpha(0.85) }
// Router snaps endpoints to the nearest passable cell within 60 cells (app/routing.py).
const SNAP_RADIUS_M = 300
const DEFAULT_MAX_SLOPE = 15

// NASA's proposed Curiosity path (reference overlay): dashed gold line + white waypoint dots.
// Dark gaps, not white: gold/white dashes vanish on the light-grey HiRISE hillshade.
const CURIOSITY_GOLD = Color.fromCssColorString('#ffcc4d')
const CURIOSITY_GAP = Color.fromCssColorString('#0a0e1a').withAlpha(0.85)
const WAYPOINT_LABEL_OFFSET = new Cartesian2(10, 0)
// 100 km: the study-area view sits at ~64 km now that the viewer box overhangs the window
// (same on-screen scale as the earlier 40 km view), and the names should show there.
const WAYPOINT_LABEL_DDC = new DistanceDisplayCondition(0, 100_000)
// USGS geologic units: semi-transparent fills (eHt blue-grey, Htu brown).
const GEO_UNIT_COLORS: Record<string, string> = { eHt: '#7f93ad', Htu: '#8b5a2b' }
export const geoUnitColor = (p: GeologicUnitProps) => GEO_UNIT_COLORS[p.unit] ?? p.color ?? '#999999'

/**
 * Heights of the rendered (exaggerated) terrain surface at a few lon/lat points, refreshed
 * whenever terrain tiles finish loading or the exaggeration changes. Used instead of Cesium's
 * HeightReference.CLAMP_TO_GROUND, which settled on wrong heights with this terrain provider.
 */
function useSurfaceHeights(viewer: CesiumViewer | undefined, points: Record<string, LonLat>, deps: unknown[]) {
  const [heights, setHeights] = useState<Record<string, number>>({})
  const pointsKey = JSON.stringify(points)
  useEffect(() => {
    if (!viewer) return
    const pts = JSON.parse(pointsKey) as Record<string, LonLat>
    const recompute = () => {
      if (viewer.isDestroyed()) return
      const next: Record<string, number> = {}
      for (const [k, p] of Object.entries(pts)) {
        if (!isLonLat(p)) continue
        const h = viewer.scene.globe.getHeight(Cartographic.fromDegrees(p.lon, p.lat))
        if (h !== undefined) next[k] = h
      }
      setHeights(prev => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
    }
    recompute()
    const off = viewer.scene.globe.tileLoadProgressEvent.addEventListener((queued: number) => { if (queued === 0) recompute() })
    const t = window.setTimeout(recompute, 1500)
    return () => { off(); window.clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewer, pointsKey, ...deps])
  return heights
}

// The live viewer, so other components (ARIA) can ask where the map is centred.
let activeViewer: CesiumViewer | undefined

/** Lon/lat of the terrain at the centre of the view (or below the camera). */
export function getMapCenter(): LonLat | null {
  const v = activeViewer
  if (!v || v.isDestroyed()) return null
  const canvas = v.scene.canvas
  const ray = v.camera.getPickRay(new Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2))
  const hit = (ray && v.scene.globe.pick(ray, v.scene)) ?? undefined
  const c = hit ? Cartographic.fromCartesian(hit, MARS) : v.camera.positionCartographic
  return { lon: +CesiumMath.toDegrees(c.longitude).toFixed(5), lat: +CesiumMath.toDegrees(c.latitude).toFixed(5) }
}

/** Fly so that `lon, lat` is at the centre of the view (where ARIA reads the position), keeping the
 *  current view angle and zoom. Returns false when the map isn't ready. */
export function centerMapOn(lon: number, lat: number): boolean {
  const v = activeViewer
  if (!v || v.isDestroyed()) return false
  const cam = v.camera, canvas = v.scene.canvas
  const ray = cam.getPickRay(new Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2))
  const hit = (ray && v.scene.globe.pick(ray, v.scene)) ?? undefined
  const hereH = hit ? Cartographic.fromCartesian(hit, MARS).height : 0
  const h = v.scene.globe.getHeight(Cartographic.fromDegrees(lon, lat)) ?? hereH
  const range = hit ? Cartesian3.distance(cam.positionWC, hit) : 4000
  cam.flyToBoundingSphere(new BoundingSphere(Cartesian3.fromDegrees(lon, lat, h, MARS), 0), {
    offset: new HeadingPitchRange(cam.heading, Math.min(cam.pitch, -0.35), Math.min(Math.max(range, 1500), 60000)),
    duration: 1.5,
  })
  return true
}

/** A colour with its alpha scaled by a layer's opacity slider (0–1). */
const fade = (c: Color, a: number) => c.withAlpha(c.alpha * a)

const isLonLat = (p: { lon: unknown; lat: unknown }) =>
  Number.isFinite(p.lon) && Number.isFinite(p.lat)
const fmtLat = (v: number) => `${Math.abs(v).toFixed(4)}°${v < 0 ? 'S' : 'N'}`
const fmtLon = (v: number) => `${Math.abs(v).toFixed(4)}°${v < 0 ? 'W' : 'E'}`

// A backend PNG layer draped on the 3D terrain as a textured ground rectangle over the
// terrain file's georeferenced bounds. (Imagery layers were tried: a single-tile layer this
// small is skipped by Cesium on coarse, distant terrain tiles, so oblique views lost it.)
function Overlay({ name, url, rect, show, zIndex, opacity }: {
  name: string; url: string | null; rect: Rectangle | null; show: boolean; zIndex: number; opacity: number
}) {
  const material = useMemo(
    () => (url ? new ImageMaterialProperty({ image: url, transparent: true }) : undefined), [url])
  // Opacity slider: tint the same material (no new texture, updates in real time).
  useEffect(() => {
    if (material) material.color = new ConstantProperty(Color.WHITE.withAlpha(opacity))
  }, [material, opacity])
  if (!url || !rect) return null
  return (
    <Entity name={name} show={show}>
      <RectangleGraphics coordinates={rect} material={material} zIndex={zIndex}
                         classificationType={ClassificationType.TERRAIN} />
    </Entity>
  )
}

/** Gale Crater sites: Curiosity's raw-image gallery on nasa.gov (opens in a new tab). */
function RawImagesLink() {
  return (
    <a className="raw-images-btn" href={CURIOSITY_RAW_IMAGES} target="_blank" rel="noreferrer">
      📷 View Curiosity Images (NASA)
    </a>
  )
}

export default function Globe({ sites }: { sites: ScienceCard[] }) {
  const ref = useRef<CesiumComponentRef<CesiumViewer>>(null)
  const [viewer, setViewer] = useState<CesiumViewer>()
  const [galeCard, setGaleCard] = useState(false)
  const [mineralCard, setMineralCard] = useState<MineralPick | null>(null)
  const [unitCard, setUnitCard] = useState<GeologicUnitProps | null>(null)
  const [waypointCard, setWaypointCard] = useState<CuriosityWaypoint | null>(null)
  const [landingCard, setLandingCard] = useState<LandingSite | null>(null)
  // The hover-info bar lives in its own layout row under the map (App.tsx #inspector-slot).
  const [inspectorSlot, setInspectorSlot] = useState<HTMLElement | null>(null)
  useEffect(() => { setInspectorSlot(document.getElementById('inspector-slot')) }, [])
  const reliefRef = useRef<ImageryLayer>()
  // 'flat' or the 3D terrain in use (labels use it to enable terrain-occlusion checks).
  const [terrainKey, setTerrainKey] = useState('flat')
  const layers = useLayerStore()
  const op = layers.opacity
  const {
    dataset, georef, terrain, ortho, minerals, geology, curiosityRoute, response, start, end, activeMode, picking,
    setStart, setEnd, setPicking, setPickMessage,
  } = useRouteStore()

  // One info card at a time.
  const closeCards = () => {
    setGaleCard(false); setMineralCard(null); setUnitCard(null); setWaypointCard(null); setLandingCard(null)
  }
  const showCard = (which: 'gale' | 'mineral' | 'unit' | 'waypoint' | 'landing', value?: unknown) => {
    setLandingCard(which === 'landing' ? value as LandingSite : null)
    setGaleCard(which === 'gale')
    setMineralCard(which === 'mineral' ? value as MineralPick : null)
    setUnitCard(which === 'unit' ? value as GeologicUnitProps : null)
    setWaypointCard(which === 'waypoint' ? value as CuriosityWaypoint : null)
  }

  // ---------- NASA reference layers ----------
  const geoUnits = useMemo(() => (geology?.features ?? []).map(f => ({
    props: f.properties,
    hierarchy: new PolygonHierarchy(Cartesian3.fromDegreesArray(f.geometry.coordinates[0].flat(), MARS)),
    base: Color.fromCssColorString(geoUnitColor(f.properties)).withAlpha(0.38),
  })), [geology])
  const geoMaterials = useMemo(() => geoUnits.map(u => fade(u.base, op.geology)), [geoUnits, op.geology])
  const curiosity = curiosityRoute?.features[0]
  const curiosityLine = useMemo(
    () => curiosity && Cartesian3.fromDegreesArray(curiosity.geometry.coordinates.flat(), MARS), [curiosity])
  const waypoints = useMemo(() => curiosity?.properties.waypoints ?? [], [curiosity])
  useEffect(() => { if (!layers.showGeology) setUnitCard(null) }, [layers.showGeology])
  useEffect(() => { if (!layers.showTraverse) setWaypointCard(null) }, [layers.showTraverse])

  const rect = useMemo(
    () => (georef ? Rectangle.fromDegrees(georef.west, georef.south, georef.east, georef.north) : null),
    [georef])

  // Grab the Cesium viewer once Resium has created it, and set up the Mars scene.
  useEffect(() => {
    const v = ref.current?.cesiumElement
    if (!v || viewer) return
    // Deep navy globe where no imagery has loaded, matching the dashboard background.
    v.scene.globe.baseColor = Color.fromCssColorString('#16213f')
    v.scene.backgroundColor = Color.fromCssColorString('#0a0e1a')
    v.scene.globe.enableLighting = false
    // Pins/labels clamp to the terrain; terrain hides what is behind it.
    v.scene.globe.depthTestAgainstTerrain = true
    // Black space with Cesium's bundled star field; no Earth sky glow, sun flare or (Earth's) moon.
    if (v.scene.skyAtmosphere) v.scene.skyAtmosphere.show = false
    v.scene.globe.showGroundAtmosphere = false
    if (v.scene.sun) v.scene.sun.show = false
    if (v.scene.moon) v.scene.moon.show = false
    v.imageryLayers.removeAll()
    v.imageryLayers.addImageryProvider(marsBasemap)
    const relief = v.imageryLayers.addImageryProvider(molaRelief)
    relief.show = useLayerStore.getState().view === 'mars'
    reliefRef.current = relief
    // Start zoomed in over Gale Crater / Bradbury Landing. The camera is never restricted:
    // users can explore the whole planet from anywhere.
    v.camera.setView({ destination: Cartesian3.fromDegrees(...START_VIEW, MARS) })
    // Dev-only test hooks (used by browser checks); stripped from production builds.
    if (import.meta.env.DEV) {
      const w = window as unknown as { __cosmicViewer: CesiumViewer; __Cesium: unknown }
      w.__cosmicViewer = v
      import('cesium').then(m => { w.__Cesium = m })
    }
    activeViewer = v
    setViewer(v)
  })

  // ---------- map frame: viewer box centred on the area not covered by panels ----------
  useEffect(() => {
    if (!viewer) return
    const update = () => { measureMapFrame(); if (!viewer.isDestroyed()) viewer.resize() }
    update()
    const ro = new ResizeObserver(update)
    for (const sel of ['.globe', '.sidebar', '.dock']) {
      const el = document.querySelector(sel)
      if (el) ro.observe(el)
    }
    window.addEventListener('resize', update)
    return () => { ro.disconnect(); window.removeEventListener('resize', update) }
  }, [viewer])

  const flyToGale = () => {
    viewer?.camera.flyTo({ destination: fitToVisible(GALE_RECT), duration: 2 })
    showCard('gale')
  }
  const flyToStudyArea = () => {
    if (viewer && rect) viewer.camera.flyTo({ destination: fitToVisible(rect), duration: 1.5 })
  }

  // ---------- top-bar tabs: Gale study area / Whole Mars ----------
  const { view, setView } = layers
  useEffect(() => { if (reliefRef.current) reliefRef.current.show = view === 'mars' }, [viewer, view])
  // Switching views changes the uncovered area (the elevation panel comes and goes), so each
  // view's camera target is computed once the new layout is applied: after React commits the
  // view change, the map frame is re-measured, Cesium picks up the new size, then it flies.
  const pendingFly = useRef<(() => void) | null>(null)
  const flyAfterLayout = (next: typeof view, fly: (v: CesiumViewer) => void) => {
    if (!viewer) return
    const run = () => { if (!viewer.isDestroyed()) { measureMapFrame(); viewer.resize(); fly(viewer) } }
    if (next === view) run()                 // same view: the layout does not change
    else pendingFly.current = run
  }
  useEffect(() => {
    const run = pendingFly.current
    if (!run) return
    pendingFly.current = null
    const id = requestAnimationFrame(run)
    return () => cancelAnimationFrame(id)
  }, [view])
  const goWholeMars = () => {
    setView('mars')
    setPicking(null)
    closeCards()
    flyAfterLayout('mars', v => v.camera.flyTo({ ...wholeMarsCamera(v), duration: 2.5 }))
  }
  const goStudyArea = () => {
    setView('study')
    closeCards()
    flyAfterLayout('study', v => {
      if (rect) v.camera.flyTo({ destination: fitToVisible(rect), duration: 2.5 })
      else v.camera.flyTo({ destination: Cartesian3.fromDegrees(...START_VIEW, MARS), duration: 2.5 })
    })
  }

  // ---------- HiRISE ortho photo mosaic (imagery tiles from the backend, toggled) ----------
  // Greyscale ~1 m/px photos, draped on the terrain above the Mars Trek basemap. Tiles are
  // cut on demand from the clipped mosaic (scripts/build_ortho_mosaic.py → app/ortho_tiles.py);
  // outside the study area nothing is requested. The layer store keeps it exclusive with the HiRISE
  // hillshade, which is an entity and would otherwise cover it.
  const orthoRect = useMemo(
    () => (ortho?.available ? Rectangle.fromDegrees(ortho.west!, ortho.south!, ortho.east!, ortho.north!) : null),
    [ortho])
  const [orthoLayer, setOrthoLayer] = useState<ImageryLayer>()
  useEffect(() => {
    if (!viewer || !dataset || !ortho || !orthoRect) return
    const layer = viewer.imageryLayers.addImageryProvider(new UrlTemplateImageryProvider({
      url: orthoTileTemplate(dataset.id, ortho.version),
      tilingScheme: new GeographicTilingScheme({ ellipsoid: MARS }),
      rectangle: orthoRect,
      maximumLevel: ortho.max_level,
      credit: new Credit(`HiRISE orthoimages ${(ortho.sources ?? []).map(f => f.slice(0, 15)).join(', ')}: ${ortho.credit}`),
    }))
    layer.show = useLayerStore.getState().showOrtho
    setOrthoLayer(layer)
    return () => {
      if (!viewer.isDestroyed()) viewer.imageryLayers.remove(layer, true)
      setOrthoLayer(undefined)
    }
  }, [viewer, dataset, ortho, orthoRect])
  useEffect(() => { if (orthoLayer) orthoLayer.show = layers.showOrtho }, [orthoLayer, layers.showOrtho])
  useEffect(() => { if (orthoLayer) orthoLayer.alpha = op.ortho }, [orthoLayer, op.ortho])
  const flyToOrtho = () => {
    if (viewer && orthoRect) viewer.camera.flyTo({ destination: fitToVisible(orthoRect), duration: 1.5 })
  }

  // ---------- 3D terrain + vertical exaggeration ----------
  useEffect(() => {
    if (!viewer) return
    const is3d = !!(dataset && terrain?.available)
    viewer.terrainProvider = is3d ? marsTerrain(dataset!.id, terrain!.tile_size) : flatTerrain
    setTerrainKey(is3d ? `3d:${dataset!.id}` : 'flat')
  }, [viewer, dataset, terrain])
  useEffect(() => {
    if (!viewer) return
    // Exaggerate relative to the study-area floor (median grid height, about -4480 m), so the
    // Gale floor stays put and relief above/below it is stretched. Display only:
    // routing and every number in the app use true heights.
    viewer.scene.verticalExaggeration = terrain?.available ? layers.exaggeration : 1
    viewer.scene.verticalExaggerationRelativeHeight = terrain?.reference_height_m ?? 0
  }, [viewer, terrain, layers.exaggeration])

  // ---------- HiRISE overlays (draped) ----------
  const hiriseUrl = dataset ? layerUrl(dataset.id, layers.hiriseStyle) : null

  // ---------- place names ----------
  // Science-site names already have their own pins; Gale has its clickable marker.
  const siteNames = useMemo(() => sites.map(s => s.site.toLowerCase()), [sites])
  const excludeLabel = useCallback(
    (f: MarsFeature) => f === GALE || (layers.showSites && siteNames.some(s => s.startsWith(f.n.toLowerCase()))),
    [siteNames, layers.showSites])
  const siteLabels = useMemo<SiteLabel[]>(
    () => sites.filter(isLonLat).map(s => ({ text: s.site, lon: s.lon, lat: s.lat })), [sites])
  const reserved = useCallback((): Reserved[] => {
    const out: Reserved[] = [{ lon: GALE.lon, lat: GALE.lat, w: 110, h: 54, dy: 8 }]
    const pin = (lon: number, lat: number) =>
      out.push({ lon, lat, w: 32, h: 42, dy: -21, maxHeight: SITE_MAX_HEIGHT })
    for (const p of [start, end]) if (isLonLat(p)) pin(p.lon, p.lat)
    if (layers.showSites) for (const s of siteLabels) pin(s.lon, s.lat)
    return out
  }, [start, end, siteLabels, layers.showSites])
  useMarsLabels(viewer, terrainKey, layers.showLabels, layers.showSites, siteLabels, excludeLabel, reserved,
    op.labels, op.sites)
  useMineralPoints(viewer, minerals, layers.showMinerals,
    terrain?.available ? layers.exaggeration : 1, terrain?.reference_height_m ?? 0, op.minerals)
  useEffect(() => { if (!layers.showMinerals) setMineralCard(null) }, [layers.showMinerals])

  // ---------- clicks: Gale marker, or validated A/B picking ----------
  const onClick = async (e: { position: Cartesian2 }) => {
    if (!viewer) return
    if (!picking) {
      const hit = viewer.scene.pick(e.position) as { id?: { id?: string } & Partial<MineralPick> } | undefined
      const id = typeof hit?.id?.id === 'string' ? hit.id.id : ''
      if (id.startsWith('gale-crater')) { if (view === 'mars') goStudyArea(); else flyToGale() }
      else if (id.startsWith('landing:')) showCard('landing', LANDING_SITES.find(s => s.id === id.slice(8)))
      else if (hit?.id?.mineral) showCard('mineral', hit.id)
      else if (id.startsWith('curiosity-wp:')) showCard('waypoint', waypoints[+id.slice(13)])
      else if (id.startsWith('geo-unit:')) showCard('unit', geoUnits.find(u => u.props.unit === id.slice(9))?.props)
      return
    }
    // Pick the terrain surface (with exaggeration, the ellipsoid point would be off).
    const ray = viewer.camera.getPickRay(e.position)
    const cart = (ray && viewer.scene.globe.pick(ray, viewer.scene)) ?? viewer.camera.pickEllipsoid(e.position, MARS)
    if (!cart) return
    const c = Cartographic.fromCartesian(cart, MARS)
    const p: LonLat = {
      lon: +CesiumMath.toDegrees(c.longitude).toFixed(5),
      lat: +CesiumMath.toDegrees(c.latitude).toFixed(5),
    }
    const target = picking
    const label = target === 'start' ? 'A' : 'B'
    const where = `${fmtLat(p.lat)}, ${fmtLon(p.lon)}`
    if (!dataset || !georef || !inGeoref(georef, p)) {
      // Picking stays active so the user can try again inside the footprint.
      setPickMessage({ target, kind: 'error', text: `${where} is outside the routable area. Pick inside the highlighted HiRISE footprint.` })
      return
    }
    setPickMessage({ target, kind: 'checking', text: `Checking ${where} against routing coverage…` })
    try {
      const lk = await getLookup(dataset.id, p)
      if (lk.status === 'ok') {
        const maxSlope = response?.params_used.max_slope_deg ?? DEFAULT_MAX_SLOPE
        const steep = (lk.slope_deg ?? 0) > maxSlope
        if (target === 'start') setStart(p); else setEnd(p)
        setPicking(null)
        setPickMessage({
          target, kind: steep ? 'warn' : 'ok',
          text: `${label} placed at ${where} · ${lk.elevation_m?.toFixed(0)} m · slope ${lk.slope_deg?.toFixed(1)}° · ${lk.elevation_source}` +
            (steep ? `. Steeper than ${maxSlope}°: the route will start from the nearest passable cell within ${SNAP_RADIUS_M} m.` : ''),
        })
      } else {
        const why = {
          nodata: 'has no elevation data',
          slope_unknown: 'is on the edge of the terrain grid (slope unknown)',
          outside_study_area: 'is outside the routing grid',
          terrain_unavailable: 'has no terrain loaded',
        }[lk.status] ?? `is not routable (${lk.status})`
        setPickMessage({ target, kind: 'error', text: `${where} ${why}. Pick another point.` })
      }
    } catch (err) {
      setPickMessage({ target, kind: 'error', text: `Could not check coverage: ${(err as Error).message}` })
    }
  }

  const footprintRing = useMemo(() => georef && Cartesian3.fromDegreesArray([
    georef.west, georef.north, georef.east, georef.north, georef.east, georef.south,
    georef.west, georef.south, georef.west, georef.north,
  ], MARS), [georef])
  const dash = useMemo(() => new PolylineDashMaterialProperty({ color: FOOTPRINT_COLOR, dashLength: 14 }), [])
  useEffect(() => { dash.color = new ConstantProperty(fade(FOOTPRINT_COLOR, op.footprint)) }, [dash, op.footprint])
  const footprintLabel = useMemo(
    () => ({ fill: fade(FOOTPRINT_COLOR, op.footprint), halo: fade(HALO, op.footprint) }), [op.footprint])
  // Curiosity route (NASA reference): dashed gold line, white waypoint dots, gold names.
  const traverseStyle = useMemo(() => {
    const a = op.traverse
    return {
      line: new PolylineDashMaterialProperty({
        color: fade(CURIOSITY_GOLD, a), gapColor: fade(CURIOSITY_GAP, a), dashLength: 20,
      }),
      dot: fade(Color.WHITE, a), gold: fade(CURIOSITY_GOLD, a), halo: fade(HALO, a),
    }
  }, [op.traverse])
  // Planned routes: both drawn, the active one stronger.
  const routeStyle = useMemo(() => {
    const a = op.route
    return {
      shortest: {
        active: new PolylineDashMaterialProperty({ color: fade(ROUTE_STYLE.shortest.color, a), dashLength: 16 }),
        dim: new PolylineDashMaterialProperty({ color: fade(ROUTE_DIM.shortest, a), dashLength: 16 }),
      },
      terrain: { active: fade(ROUTE_STYLE.terrain.color, a), dim: fade(ROUTE_DIM.terrain, a) },
    }
  }, [op.route])
  const siteTint = useMemo(() => fade(Color.WHITE, op.sites), [op.sites])
  const pickTint = useMemo(() => FOOTPRINT_COLOR.withAlpha(0.18), [])
  const showFootprint = layers.showFootprint || !!picking

  // Ground heights for pins / markers on the rendered terrain.
  const hsPoints = useMemo(() => {
    const pts: Record<string, LonLat> = { gale: { lon: GALE.lon, lat: GALE.lat }, start, end }
    if (georef) pts.footprint = { lon: (georef.west + georef.east) / 2, lat: georef.north }
    for (const s of sites) if (isLonLat(s)) pts[`site:${s.card_id}`] = { lon: s.lon, lat: s.lat }
    waypoints.forEach((w, i) => { pts[`wp:${i}`] = { lon: w.lon, lat: w.lat } })
    for (const s of LANDING_SITES) pts[`land:${s.id}`] = { lon: s.lon, lat: s.lat }
    return pts
  }, [start, end, georef, sites, waypoints])
  const hs = useSurfaceHeights(viewer, hsPoints, [terrainKey, layers.exaggeration])

  const routes = response?.routes ?? {}
  return (
    <>
      <Viewer
        ref={ref}
        className="cesium-host"
        terrainProvider={flatTerrain}
        baseLayer={false}
        baseLayerPicker={false}
        geocoder={false}
        homeButton={false}
        sceneModePicker={false}
        navigationHelpButton={false}
        animation={false}
        timeline={false}
        fullscreenButton={false}
        infoBox={false}
        selectionIndicator={false}
        style={{ cursor: picking ? 'crosshair' : undefined }}
      >
        <ScreenSpaceEventHandler>
          <ScreenSpaceEvent action={onClick as never} type={ScreenSpaceEventType.LEFT_CLICK} />
        </ScreenSpaceEventHandler>

        {/* HiRISE terrain draped on the terrain surface. */}
        <Overlay name="HiRISE terrain" url={hiriseUrl} rect={rect} show={layers.showHiRISE} zIndex={0} opacity={op.hirise} />

        {/* Routable footprint = the analysis grid (every cell has elevation; only the outer
            1-cell border lacks slope). Tinted while picking A/B. */}
        {footprintRing && rect && (
          <Entity name="Routable area" show={showFootprint}>
            <PolylineGraphics positions={footprintRing} width={2.5} material={dash} clampToGround />
          </Entity>
        )}
        {rect && (
          <Entity name="Routable area (picking)" show={!!picking}>
            <RectangleGraphics coordinates={rect} material={pickTint} zIndex={2} classificationType={ClassificationType.TERRAIN} />
          </Entity>
        )}
        {georef && (
          <Entity name="Routable area label" show={showFootprint}
                  position={Cartesian3.fromDegrees((georef.west + georef.east) / 2, georef.north, hs.footprint ?? 0, MARS)}>
            <LabelGraphics text="ROUTABLE AREA" font="600 11px 'Space Grotesk', sans-serif"
                           fillColor={footprintLabel.fill} outlineColor={footprintLabel.halo} outlineWidth={3} style={2}
                           verticalOrigin={VerticalOrigin.BOTTOM} pixelOffset={FOOTPRINT_LABEL_OFFSET}
                           distanceDisplayCondition={FOOTPRINT_LABEL_DDC}
                           disableDepthTestDistance={NEAR_NO_DEPTH} />
          </Entity>
        )}

        {/* USGS geologic map units (Tanaka et al. 2014, SIM 3292), draped on the terrain. */}
        {geoUnits.map((u, i) => (
          <Entity key={u.props.unit} id={`geo-unit:${u.props.unit}`} name={u.props.name} show={layers.showGeology}>
            <PolygonGraphics hierarchy={u.hierarchy} material={geoMaterials[i]} zIndex={3}
                             classificationType={ClassificationType.TERRAIN} />
          </Entity>
        ))}

        {/* NASA's proposed Curiosity path up Mount Sharp (reference overlay). */}
        {/* Keyed on terrain + exaggeration: the route data usually arrives before the 3D
            terrain is switched on, and a ground-clamped line built before that switch was
            never drawn. Re-creating it (6 points) after each terrain change fixes that. */}
        {curiosityLine && (
          <Entity key={`curiosity-line:${terrainKey}:${layers.exaggeration}`}
                  name="Curiosity official route (NASA JPL)" show={layers.showTraverse}>
            <PolylineGraphics positions={curiosityLine} width={5} material={traverseStyle.line} clampToGround />
          </Entity>
        )}
        {waypoints.map((w, i) => (
          <Entity key={w.name} id={`curiosity-wp:${i}`} name={w.name} show={layers.showTraverse}
                  position={Cartesian3.fromDegrees(w.lon, w.lat, hs[`wp:${i}`] ?? 0, MARS)}>
            <PointGraphics pixelSize={9} color={traverseStyle.dot} outlineColor={traverseStyle.gold} outlineWidth={2.5}
                           disableDepthTestDistance={NEAR_NO_DEPTH} distanceDisplayCondition={LOCAL_ONLY} />
            <LabelGraphics text={w.name} font="600 11px 'Space Grotesk', sans-serif"
                           fillColor={traverseStyle.gold} outlineColor={traverseStyle.halo} outlineWidth={3} style={2}
                           horizontalOrigin={HorizontalOrigin.LEFT} pixelOffset={WAYPOINT_LABEL_OFFSET}
                           distanceDisplayCondition={WAYPOINT_LABEL_DDC} disableDepthTestDistance={NEAR_NO_DEPTH} />
          </Entity>
        ))}

        {layers.showRoute && (['shortest', 'terrain'] as const).map(m => {
          const r = routes[m]
          if (!r) return null
          const style = ROUTE_STYLE[m]
          const active = m === activeMode
          const material = active ? routeStyle[m].active : routeStyle[m].dim
          return (
            <Entity key={`${m}:${terrainKey}`} name={`${m} route`}>
              <PolylineGraphics
                positions={Cartesian3.fromDegreesArray(r.lonlat.flat(), MARS)}
                clampToGround
                width={active ? style.width + 2 : style.width}
                material={material}
              />
            </Entity>
          )
        })}

        {/* Clickable Gale Crater marker at the IAU centre (5.37°S, 137.81°E). */}
        <Entity id="gale-crater" name="Gale Crater"
                position={Cartesian3.fromDegrees(GALE.lon, GALE.lat, hs.gale ?? 0, MARS)}>
          <BillboardGraphics image={GALE_ICON} disableDepthTestDistance={NEAR_NO_DEPTH * 25} />
          <LabelGraphics text="Gale Crater" font="700 14px 'Space Grotesk', sans-serif"
                         fillColor={INK} outlineColor={HALO} outlineWidth={4} style={2}
                         verticalOrigin={VerticalOrigin.TOP} pixelOffset={GALE_LABEL_OFFSET}
                         disableDepthTestDistance={NEAR_NO_DEPTH * 25} />
        </Entity>

        {/* Whole Mars view: NASA landing sites (approximate positions, src/data/landingSites.ts). */}
        {LANDING_SITES.map(s => (
          <Entity key={s.id} id={`landing:${s.id}`} name={s.mission} show={view === 'mars'}
                  position={Cartesian3.fromDegrees(s.lon, s.lat, hs[`land:${s.id}`] ?? 0, MARS)}>
            <BillboardGraphics image={LANDING_ICON} disableDepthTestDistance={NEAR_NO_DEPTH * 25} />
            <LabelGraphics text={`${s.mission.split(' (')[0]} · ${s.year}`} font="600 12px 'Space Grotesk', sans-serif"
                           fillColor={LANDING_TEAL} outlineColor={HALO} outlineWidth={3} style={2}
                           horizontalOrigin={HorizontalOrigin.LEFT} pixelOffset={LANDING_LABEL_OFFSET}
                           disableDepthTestDistance={NEAR_NO_DEPTH * 25} />
          </Entity>
        ))}

        {/* Route endpoints (skipped while an input is half-typed / empty) */}
        {isLonLat(start) && (
          <Entity name="Start" position={Cartesian3.fromDegrees(start.lon, start.lat, hs.start ?? 0, MARS)}>
            <BillboardGraphics image={START_PIN} verticalOrigin={VerticalOrigin.BOTTOM} disableDepthTestDistance={NEAR_NO_DEPTH} distanceDisplayCondition={LOCAL_ONLY} />
          </Entity>
        )}
        {isLonLat(end) && (
          <Entity name="Destination" position={Cartesian3.fromDegrees(end.lon, end.lat, hs.end ?? 0, MARS)}>
            <BillboardGraphics image={END_PIN} verticalOrigin={VerticalOrigin.BOTTOM} disableDepthTestDistance={NEAR_NO_DEPTH} distanceDisplayCondition={LOCAL_ONLY} />
          </Entity>
        )}

        {/* Science sites from /api/science/cards (some cards have no coordinates).
            Their names are drawn by the label declutter (MarsLabels) so they never overlap. */}
        {layers.showSites && sites.filter(isLonLat).map(s => (
          <Entity key={s.card_id} name={s.site} description={s.summary}
                  position={Cartesian3.fromDegrees(s.lon, s.lat, hs[`site:${s.card_id}`] ?? 0, MARS)}>
            <BillboardGraphics image={SITE_PIN} verticalOrigin={VerticalOrigin.BOTTOM} color={siteTint}
                               disableDepthTestDistance={NEAR_NO_DEPTH} distanceDisplayCondition={LOCAL_ONLY} />
          </Entity>
        ))}
      </Viewer>

      {inspectorSlot && createPortal(<Inspector viewer={viewer} />, inspectorSlot)}
      {/* Globe tools (top-right) */}
      <div className="globe-tools" data-occludes>
        <div className="view-tabs" role="tablist" aria-label="Map view">
          <button role="tab" aria-selected={view === 'study'} className={view === 'study' ? 'on' : ''}
                  onClick={goStudyArea}>Gale study area</button>
          <button role="tab" aria-selected={view === 'mars'} className={view === 'mars' ? 'on' : ''}
                  onClick={goWholeMars}>🪐 Whole Mars</button>
        </div>
        {view === 'study' && <>
          <button className="glass-btn" onClick={flyToGale}>Go to Gale Crater</button>
          <button className="glass-btn ghost" onClick={flyToStudyArea} disabled={!rect}>Study area</button>
        </>}
        {layers.showOrtho && orthoRect && (
          <button className="glass-btn ghost" onClick={flyToOrtho}>HiRISE photo</button>
        )}
      </div>
      {picking && (
        <div className="pick-banner glass" data-occludes>
          Click inside the <b>routable area</b> to place <b>{picking === 'start' ? 'A' : 'B'}</b> · drag to explore
          <button className="link" onClick={() => setPicking(null)}>Cancel</button>
        </div>
      )}
      {mineralCard && (
        <div className="info-card glass" data-occludes>
          <button className="close" aria-label="Close" onClick={() => setMineralCard(null)}>×</button>
          <h3>{mineralCard.label}</h3>
          <dl>
            <dt>Class</dt><dd><i className="swatch" style={{ background: mineralCard.color }} />{mineralCard.mineral.c}</dd>
            <dt>Site</dt><dd>{fmtLat(mineralCard.mineral.lat)}, {fmtLon(mineralCard.mineral.lon)} (±~0.01°)</dd>
            <dt>Instruments</dt><dd>{minerals?.instruments?.join(', ')}</dd>
          </dl>
          <p className="src">{minerals?.nature}</p>
          <p className="src">Source: {minerals?.citation} Via NASA Mars Trek.</p>
        </div>
      )}
      {galeCard && (
        <div className="info-card glass" data-occludes>
          <button className="close" aria-label="Close" onClick={() => setGaleCard(false)}>×</button>
          <h3>Gale Crater</h3>
          <dl>
            <dt>Type</dt><dd>Impact crater (IAU: {GALE.t})</dd>
            <dt>Diameter</dt><dd>{GALE.d.toFixed(0)} km</dd>
            <dt>Centre</dt><dd>{fmtLat(GALE.lat)}, {fmtLon(GALE.lon)}</dd>
            <dt>Inside</dt><dd>Aeolis Mons (Mount Sharp), Aeolis Palus, Curiosity's landing site</dd>
          </dl>
          <p className="src">Source: <a href={featureUrl(GALE)} target="_blank" rel="noreferrer">IAU/USGS Gazetteer</a></p>
          <button className="primary" onClick={() => { flyToStudyArea(); setGaleCard(false) }} disabled={!rect}>
            Zoom to routable area
          </button>
          <RawImagesLink />
        </div>
      )}
      {unitCard && (
        <div className="info-card glass" data-occludes>
          <button className="close" aria-label="Close" onClick={() => setUnitCard(null)}>×</button>
          <h3>{unitCard.name}</h3>
          <dl>
            <dt>Unit</dt><dd><i className="swatch square" style={{ background: geoUnitColor(unitCard) }} />{unitCard.unit}</dd>
            <dt>Age</dt><dd>{unitCard.age}</dd>
          </dl>
          <p className="desc">{unitCard.description}</p>
          {geology?.properties?.caveat && <p className="src">{geology.properties.caveat}</p>}
          <p className="src">Source: <a href={unitCard.url} target="_blank" rel="noreferrer">{unitCard.source}</a></p>
        </div>
      )}
      {waypointCard && (
        <div className="info-card glass" data-occludes>
          <button className="close" aria-label="Close" onClick={() => setWaypointCard(null)}>×</button>
          <h3>{waypointCard.name}</h3>
          <dl>
            <dt>Science</dt><dd>{waypointCard.note}</dd>
            <dt>Position</dt><dd>{fmtLat(waypointCard.lat)}, {fmtLon(waypointCard.lon)} (approx.)</dd>
          </dl>
          {curiosity?.properties.coordinate_note && <p className="src">{curiosity.properties.coordinate_note}</p>}
          <p className="src">Source: <a href={curiosity?.properties.url} target="_blank" rel="noreferrer">
            NASA JPL — Curiosity's Proposed Path up Mount Sharp</a></p>
          <RawImagesLink />
        </div>
      )}

      {landingCard && (
        <div className="info-card glass" data-occludes>
          <button className="close" aria-label="Close" onClick={() => setLandingCard(null)}>×</button>
          <h3>{landingCard.mission}</h3>
          <dl>
            <dt>Landed</dt><dd>{landingCard.year} · {landingCard.vehicle}</dd>
            <dt>Site</dt><dd>{landingCard.place}</dd>
            <dt>Position</dt><dd>{fmtLat(landingCard.lat)}, {fmtLon(landingCard.lon)} (approx.)</dd>
          </dl>
          <p className="desc">{landingCard.note}</p>
          {landingCard.id === 'curiosity' && (
            <button className="primary" onClick={goStudyArea}>Go to the Gale study area</button>
          )}
        </div>
      )}
      {view === 'mars' && (
        <div className="mars-legend glass" data-occludes>
          <strong>Whole Mars</strong>
          <span><i className="relief-bar" />MOLA relief: low → high</span>
          <span><i className="landing-dot" />NASA landing sites · click for details</span>
          <span>Click the <b>Gale Crater</b> marker to return to the study area</span>
        </div>
      )}

      {/* Basemap attribution (bottom-right of the map). */}
      <a className="trek-credit" href={MARS_TREK_URL} target="_blank" rel="noreferrer" data-occludes>
        🛰️ Map imagery: NASA Mars Trek | trek.nasa.gov/mars
      </a>
    </>
  )
}
