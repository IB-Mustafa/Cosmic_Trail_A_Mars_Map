// Every name on the globe, in one decluttered label collection, styled by src/labelStyle.ts:
//
//   marker labels  NASA landing sites → science sites → Curiosity waypoints → mineral detections
//   place names    IAU/USGS gazetteer (src/data/mars_labels.json): Gale Crater's own features first,
//                  then the rest largest-first
//
// Level of detail: a marker category is shown below its camera height (labelStyle CATEGORY.maxHeight);
// a place name is eligible when its diameter is at least camera-height / 40 (globe view ≈ 10 000 km
// up → features ≥ 250 km; 50 km up → ≥ 1.25 km).
//
// Overlaps: UI panels (data-occludes), reserved boxes (Gale marker, A/B pins) and every visible
// marker are blocked first; labels are then placed in priority order. A marker label tries the
// right of its marker, then the left; if both collide it is hidden. Place names are centred on the
// feature and hidden on collision. Labels carry the marker's pick id, so clicking a name opens the
// same info card as clicking its marker.
import { useEffect, useRef } from 'react'
import {
  Cartesian2, Cartesian3, Cartographic, HorizontalOrigin, LabelCollection, Ray, SceneTransforms,
  VerticalOrigin, type Label, type Viewer as CesiumViewer,
} from 'cesium'
import { GALE, GAZETTEER, MARS, MARS_RADIUS, type MarsFeature } from '../mars'
import { CATEGORY, fontFor, labelOptions, measureLabel, scaleAt, type LabelCategory } from '../labelStyle'

const LOD_DIVISOR = 40          // eligible if diameter_m >= cameraHeight / LOD_DIVISOR
const MIN_DIAMETER_KM = 0.2     // features with no diameter in the gazetteer
const MAX_LABELS = 140          // place names at once
const PAD = 4                   // px gap kept between labels
const GALE_AREA_KM = 120        // gazetteer features this close to Gale's centre are placed first
export const SITE_MAX_HEIGHT = CATEGORY.site.maxHeight  // m — science sites / A-B pins only below this

/** A screen area labels must avoid (A/B pins, the Gale marker…), anchored on the terrain at lon/lat. */
export interface Reserved { lon: number; lat: number; w: number; h: number; dy: number; maxHeight?: number }

export type PointCategory = 'landing' | 'site' | 'waypoint' | 'mineral'

/** A marker's name, drawn beside the marker. */
export interface PointLabel {
  key: string
  text: string
  lon: number
  lat: number
  cat: PointCategory
  /** What scene.pick returns for this label (the marker's id), so a click opens the marker's card. */
  pickId?: unknown
  /** The marker's own box (px) around its anchor; no label may cover it. */
  marker: { w: number; h: number; dy: number }
  /** Anchor height (m) when the marker is not on the rendered terrain (mineral points). */
  height?: number
}

interface Box { x0: number; y0: number; x1: number; y1: number }
const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1

const PRIORITY: Record<PointCategory, number> = { landing: 0, site: 1, waypoint: 2, mineral: 3 }

interface Item {
  cat: LabelCategory
  point?: PointLabel
  label: Label
  pos: Cartesian3
  carto: Cartographic
  groundH: number
  w: number
  h: number
  dEff: number
  side: string | null   // current placement (side + gap), to avoid re-setting unchanged label props
}

const galeKm = (f: MarsFeature) => {
  const p1 = f.lat * Math.PI / 180, p2 = GALE.lat * Math.PI / 180
  const dl = (f.lon - GALE.lon) * Math.PI / 180
  return Math.acos(Math.min(1, Math.sin(p1) * Math.sin(p2) + Math.cos(p1) * Math.cos(p2) * Math.cos(dl))) * MARS_RADIUS / 1000
}

export function useMarsLabels(
  viewer: CesiumViewer | undefined,
  /** Changes when the terrain provider changes; labels are re-created so they re-clamp. */
  terrainKey: string,
  showNames: boolean,
  visible: Record<PointCategory, boolean>,
  points: PointLabel[],
  exclude: (f: MarsFeature) => boolean,
  reserved: () => Reserved[],
) {
  const showRef = useRef(showNames)
  const visibleRef = useRef(visible)
  const reservedRef = useRef(reserved)
  showRef.current = showNames
  visibleRef.current = visible
  reservedRef.current = reserved
  const updateRef = useRef<() => void>(() => {})

  useEffect(() => {
    if (!viewer) return
    let disposed = false
    let collection: LabelCollection | null = null
    let removeListener: (() => void) | null = null
    const items: Item[] = []
    const scratch = new Cartesian2()
    const is3d = terrainKey !== 'flat'
    // Is the anchor hidden behind (3D) terrain? Ray from the camera through the anchor: if the
    // terrain is hit clearly before it, it is hidden.
    const occluded = (it: Item) => {
      const scene = viewer.scene
      const cam = viewer.camera.positionWC
      const dir = Cartesian3.normalize(Cartesian3.subtract(it.pos, cam, new Cartesian3()), new Cartesian3())
      const hit = scene.globe.pick(new Ray(cam, dir), scene)
      if (!hit) return false
      const d = Cartesian3.distance(cam, it.pos)
      return Cartesian3.distance(cam, hit) < d - Math.max(150, d * 0.01)
    }
    const R2 = MARS_RADIUS * MARS_RADIUS
    let lastRun = 0
    let dirty = true
    const lastCam = new Cartesian3()
    const lastDir = new Cartesian3()

    const update = () => {
      if (!collection) return
      lastRun = performance.now()
      dirty = false
      const scene = viewer.scene
      const cam = viewer.camera
      const camPos = cam.positionWC
      const h = cam.positionCartographic.height
      const minKm = h / LOD_DIVISOR / 1000
      const near2 = (Math.max(h, 20_000) * 6) ** 2       // marker labels only this close to the camera
      const vis = visibleRef.current
      const width = scene.canvas.clientWidth, height = scene.canvas.clientHeight
      const placed: Box[] = []
      // On-screen part of the canvas (the viewer box may overhang the window), and the UI panels.
      const canvasRect = scene.canvas.getBoundingClientRect()
      const vx0 = Math.max(0, -canvasRect.left), vy0 = Math.max(0, -canvasRect.top)
      const vx1 = Math.min(width, window.innerWidth - canvasRect.left)
      const vy1 = Math.min(height, window.innerHeight - canvasRect.top)
      document.querySelectorAll('[data-occludes]').forEach(el => {
        const b = el.getBoundingClientRect()
        if (b.width && b.height) placed.push({ x0: b.left - canvasRect.left, x1: b.right - canvasRect.left, y0: b.top - canvasRect.top, y1: b.bottom - canvasRect.top })
      })
      const screen = (pos: Cartesian3) => SceneTransforms.worldToWindowCoordinates(scene, pos, scratch)
      // Reserved pin / marker boxes first so names never cover them.
      for (const r of reservedRef.current()) {
        if (r.maxHeight !== undefined && h > r.maxHeight) continue
        const carto = Cartographic.fromDegrees(r.lon, r.lat)
        const position = Cartesian3.fromRadians(carto.longitude, carto.latitude, scene.globe.getHeight(carto) ?? 0, MARS)
        if (Cartesian3.dot(position, camPos) <= R2 * 0.99) continue
        const p = screen(position)
        if (p) placed.push({ x0: p.x - r.w / 2, x1: p.x + r.w / 2, y0: p.y + r.dy - r.h / 2, y1: p.y + r.dy + r.h / 2 })
      }
      // Eligible marker labels: on the near side, close enough, category shown and zoomed in enough.
      const live: Item[] = []
      for (const it of items) {
        it.label.show = false
        const pt = it.point
        if (!pt || !vis[pt.cat] || h > CATEGORY[pt.cat].maxHeight) continue
        if (Cartesian3.dot(it.pos, camPos) <= R2 || Cartesian3.distanceSquared(it.pos, camPos) > near2) continue
        if (pt.height === undefined) {      // sit on the rendered terrain
          const gh = scene.globe.getHeight(it.carto) ?? 0
          if (Math.abs(gh - it.groundH) > 0.5) {
            it.groundH = gh
            it.pos = Cartesian3.fromRadians(it.carto.longitude, it.carto.latitude, gh, MARS)
            it.label.position = it.pos
          }
        }
        const p = screen(it.pos)
        if (!p || p.x < vx0 || p.y < vy0 || p.x > vx1 || p.y > vy1) continue
        const m = pt.marker
        placed.push({ x0: p.x - m.w / 2, x1: p.x + m.w / 2, y0: p.y + m.dy - m.h / 2, y1: p.y + m.dy + m.h / 2 })
        live.push(it)
      }
      const fits = (b: Box) => b.x0 > vx0 && b.y0 > vy0 && b.x1 < vx1 && b.y1 < vy1 && !placed.some(o => overlaps(o, b))
      // Marker labels in priority order: right of the marker, else left, else a little further out
      // on either side (clears an A/B pin standing on the same spot), else hidden. A name already
      // shown close by (a science site that is also a Curiosity waypoint) is not repeated.
      const shownAt = new Map<string, { x: number; y: number }>()
      for (const it of live) {
        const pt = it.point!
        const s = CATEGORY[pt.cat]
        const p = screen(it.pos)
        if (!p || (is3d && h < 1_000_000 && occluded(it))) continue
        const twin = shownAt.get(pt.text)
        if (twin && Math.hypot(twin.x - p.x, twin.y - p.y) < 80) continue
        const k = scaleAt(pt.cat, Cartesian3.distance(camPos, it.pos))
        const W = it.w * k, H = it.h * k, cy = p.y + (s.dy ?? 0)
        const y0 = cy - H / 2 - PAD, y1 = cy + H / 2 + PAD
        let chosen: { box: Box; side: 'R' | 'L'; gap: number } | null = null
        for (const gap of [s.gap ?? 10, (s.gap ?? 10) + 14]) {
          const right = { x0: p.x + gap - PAD, x1: p.x + gap + W + PAD, y0, y1 }
          const left = { x0: p.x - gap - W - PAD, x1: p.x - gap + PAD, y0, y1 }
          chosen = fits(right) ? { box: right, side: 'R', gap } : fits(left) ? { box: left, side: 'L', gap } : null
          if (chosen) break
        }
        if (!chosen) continue
        placed.push(chosen.box)
        shownAt.set(pt.text, { x: p.x, y: p.y })
        const key = `${chosen.side}${chosen.gap}`
        if (key !== it.side) {
          it.side = key
          it.label.horizontalOrigin = chosen.side === 'R' ? HorizontalOrigin.LEFT : HorizontalOrigin.RIGHT
          it.label.pixelOffset = new Cartesian2(chosen.side === 'R' ? chosen.gap : -chosen.gap, s.dy ?? 0)
        }
        it.label.show = true
      }
      // Place names: Gale's features first, then largest first.
      let shown = 0
      if (showRef.current) {
        for (const it of items) {
          if (it.point || shown >= MAX_LABELS || it.dEff < minKm) continue
          if (Cartesian3.dot(it.pos, camPos) <= R2) continue
          const gh = scene.globe.getHeight(it.carto) ?? 0
          if (Math.abs(gh - it.groundH) > 0.5) {
            it.groundH = gh
            it.pos = Cartesian3.fromRadians(it.carto.longitude, it.carto.latitude, gh, MARS)
            it.label.position = it.pos
          }
          const p = screen(it.pos)
          if (!p) continue
          const k = scaleAt(it.cat, Cartesian3.distance(camPos, it.pos))
          const W = it.w * k, H = it.h * k
          const box = { x0: p.x - W / 2 - PAD, x1: p.x + W / 2 + PAD, y0: p.y - H / 2 - PAD, y1: p.y + H / 2 + PAD }
          if (!fits(box) || (is3d && h < 1_000_000 && occluded(it))) continue
          placed.push(box)
          it.label.show = true
          shown++
        }
      }
    }
    updateRef.current = () => { dirty = true }

    // Wait for the label font so labels are rasterised with it (it is bundled locally).
    Promise.all((['region', 'feature', 'minor', 'landing'] as const).map(c => document.fonts.load(fontFor(c))))
      .catch(() => undefined).finally(() => {
        if (disposed || viewer.isDestroyed()) return
        collection = viewer.scene.primitives.add(new LabelCollection({ scene: viewer.scene }))
        const add = (cat: LabelCategory, text: string, lon: number, lat: number, hgt: number, id?: unknown) => {
          const pos = Cartesian3.fromDegrees(lon, lat, hgt, MARS)
          const label = collection!.add({
            ...labelOptions(cat), position: pos, text, id,
            horizontalOrigin: HorizontalOrigin.CENTER, verticalOrigin: VerticalOrigin.CENTER, show: false,
          })
          const { w, h } = measureLabel(cat, text)
          return { label, pos, carto: Cartographic.fromDegrees(lon, lat), w, h }
        }
        const sorted = [...points].sort((a, b) => PRIORITY[a.cat] - PRIORITY[b.cat])
        for (const pt of sorted) {
          const b = add(pt.cat, pt.text, pt.lon, pt.lat, pt.height ?? 0, pt.pickId)
          items.push({ ...b, cat: pt.cat, point: pt, groundH: pt.height ?? 0, dEff: Infinity, side: null })
        }
        const names = GAZETTEER.features.filter(f => !exclude(f))
          .map(f => ({ f, gale: galeKm(f) <= GALE_AREA_KM }))
          .sort((a, b) => Number(b.gale) - Number(a.gale) || b.f.d - a.f.d)
        for (const { f } of names) {
          const cat: LabelCategory = f.d >= 1000 ? 'region' : f.d >= 50 ? 'feature' : 'minor'
          const b = add(cat, CATEGORY[cat].upper ? f.n.toUpperCase() : f.n, f.lon, f.lat, 0)
          items.push({ ...b, cat, groundH: 0, dEff: Math.max(f.d, MIN_DIAMETER_KM), side: null })
        }
        // Re-declutter when the camera moves (throttled to ~8 Hz), and when terrain tiles finish
        // loading (ground heights may have changed).
        const offTiles = viewer.scene.globe.tileLoadProgressEvent.addEventListener((queued: number) => { if (queued === 0) dirty = true })
        const offRender = viewer.scene.postRender.addEventListener(() => {
          const c = viewer.camera
          if (!Cartesian3.equalsEpsilon(c.positionWC, lastCam, 0, 1) ||
              !Cartesian3.equalsEpsilon(c.directionWC, lastDir, 1e-6)) {
            Cartesian3.clone(c.positionWC, lastCam)
            Cartesian3.clone(c.directionWC, lastDir)
            dirty = true
          }
          if (dirty && performance.now() - lastRun > 120) update()
        })
        removeListener = () => { offTiles(); offRender() }
        update()
      })

    return () => {
      disposed = true
      removeListener?.()
      if (collection && !viewer.isDestroyed()) viewer.scene.primitives.remove(collection)
    }
  }, [viewer, terrainKey, exclude, points])

  // Toggles / reserved changes → re-run on the next frame.
  useEffect(() => { updateRef.current() }, [showNames, visible, reserved])
}
