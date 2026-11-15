// IAU/USGS place names on the globe (bundled: src/data/mars_labels.json).
//
// Level of detail: a feature is eligible when its diameter is at least
// camera-height / 40 (globe view ≈ 10 000 km up → features ≥ 250 km; 50 km up →
// ≥ 1.25 km). Eligible labels are placed largest-first; any label whose screen box
// would overlap one already placed (or a reserved pin/marker box, or a UI panel
// marked data-occludes) is hidden. Science-site names are placed before gazetteer
// names, and only when zoomed in (camera below SITE_MAX_HEIGHT).
import { useEffect, useRef } from 'react'
import {
  Cartesian2, Cartesian3, Cartographic, Color, HorizontalOrigin, LabelCollection,
  LabelStyle, Ray, SceneTransforms, VerticalOrigin, type Label, type Viewer as CesiumViewer,
} from 'cesium'
import { GAZETTEER, MARS, MARS_RADIUS, type MarsFeature } from '../mars'

const LOD_DIVISOR = 40          // eligible if diameter_m >= cameraHeight / LOD_DIVISOR
const MIN_DIAMETER_KM = 0.2     // features with no diameter in the gazetteer
const MAX_LABELS = 140
const PAD = 4                   // px gap kept between labels
export const SITE_MAX_HEIGHT = 400_000  // m — science sites / A-B pins only below this

interface Tier { font: string; px: number; color: Color; upper: boolean; widthFactor: number }
const TIERS: Tier[] = [
  { font: "600 15px 'Space Grotesk', sans-serif", px: 15, color: Color.fromCssColorString('#dce8ff'), upper: true, widthFactor: 0.7 },
  { font: "500 13px 'Space Grotesk', sans-serif", px: 13, color: Color.fromCssColorString('#e8f0ff'), upper: false, widthFactor: 0.56 },
  { font: "500 12px 'Space Grotesk', sans-serif", px: 12, color: Color.fromCssColorString('#b9c8e8'), upper: false, widthFactor: 0.56 },
]
const tierFor = (d: number) => TIERS[d >= 1000 ? 0 : d >= 50 ? 1 : 2]

/** A screen area labels must avoid (pins, the Gale marker…), anchored on the terrain at lon/lat. */
export interface Reserved { lon: number; lat: number; w: number; h: number; dy: number; maxHeight?: number }

/** A name drawn above a pin (science sites), placed before gazetteer names. */
export interface SiteLabel { text: string; lon: number; lat: number }

const SITE_FONT = "500 13px 'Space Grotesk', sans-serif"
const SITE_DY = -56   // px: name clears the tallest pin (40 px A/B) plus padding

interface Box { x0: number; y0: number; x1: number; y1: number }
const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1

export function useMarsLabels(
  viewer: CesiumViewer | undefined,
  /** Changes when the terrain provider changes; labels are re-created so they re-clamp. */
  terrainKey: string,
  show: boolean,
  showSites: boolean,
  sites: SiteLabel[],
  exclude: (f: MarsFeature) => boolean,
  reserved: () => Reserved[],
  /** Opacity sliders (0–1): gazetteer place names, science-site names. */
  labelAlpha = 1,
  siteAlpha = 1,
) {
  const showRef = useRef(show)
  const showSitesRef = useRef(showSites)
  const reservedRef = useRef(reserved)
  showRef.current = show
  showSitesRef.current = showSites
  reservedRef.current = reserved
  const updateRef = useRef<() => void>(() => {})
  const alphaRef = useRef({ labelAlpha, siteAlpha })
  alphaRef.current = { labelAlpha, siteAlpha }
  const applyAlphaRef = useRef<() => void>(() => {})

  useEffect(() => {
    if (!viewer) return
    let disposed = false
    let collection: LabelCollection | null = null
    let removeListener: (() => void) | null = null
    // Site items first (site: true), then gazetteer features largest-first.
    const items: { site: boolean; label: Label; fill: Color; halo: Color; pos: Cartesian3; carto: Cartographic; groundH: number; w: number; h: number; dy: number; dEff: number }[] = []
    // Opacity sliders: scale each label's own fill / halo alpha.
    const applyAlpha = () => {
      const { labelAlpha: la, siteAlpha: sa } = alphaRef.current
      for (const it of items) {
        const a = it.site ? sa : la
        it.label.fillColor = it.fill.withAlpha(it.fill.alpha * a)
        it.label.outlineColor = it.halo.withAlpha(it.halo.alpha * a)
      }
    }
    applyAlphaRef.current = applyAlpha

    const scratch = new Cartesian2()
    const is3d = terrainKey !== 'flat'
    // Is the label's ground point hidden behind (exaggerated) terrain? Ray from the camera
    // through the label anchor: if the terrain is hit clearly before the anchor, it is hidden.
    const occluded = (it: { carto: Cartographic }) => {
      const scene = viewer.scene
      const gh = scene.globe.getHeight(it.carto) ?? 0
      const ground = Cartesian3.fromRadians(it.carto.longitude, it.carto.latitude, gh, MARS)
      const cam = viewer.camera.positionWC
      const dir = Cartesian3.normalize(Cartesian3.subtract(ground, cam, new Cartesian3()), new Cartesian3())
      const hit = scene.globe.pick(new Ray(cam, dir), scene)
      if (!hit) return false
      const dGround = Cartesian3.distance(cam, ground)
      return Cartesian3.distance(cam, hit) < dGround - Math.max(150, dGround * 0.01)
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
      collection.show = true
      const cam = viewer.camera
      const camPos = cam.positionWC
      const h = cam.positionCartographic.height
      const minKm = h / LOD_DIVISOR / 1000
      const width = scene.canvas.clientWidth, height = scene.canvas.clientHeight
      const placed: Box[] = []
      // UI panels floating over the globe.
      const canvasRect = scene.canvas.getBoundingClientRect()
      // On-screen part of the canvas (the viewer box may overhang the window).
      const vx0 = Math.max(0, -canvasRect.left), vy0 = Math.max(0, -canvasRect.top)
      const vx1 = Math.min(width, window.innerWidth - canvasRect.left)
      const vy1 = Math.min(height, window.innerHeight - canvasRect.top)
      document.querySelectorAll('[data-occludes]').forEach(el => {
        const b = el.getBoundingClientRect()
        if (b.width && b.height) placed.push({ x0: b.left - canvasRect.left, x1: b.right - canvasRect.left, y0: b.top - canvasRect.top, y1: b.bottom - canvasRect.top })
      })
      // Reserve pin / marker boxes first so names never cover them.
      for (const r of reservedRef.current()) {
        if (r.maxHeight !== undefined && h > r.maxHeight) continue
        // Pins are clamped to the (exaggerated) terrain: use the rendered surface height.
        const carto = Cartographic.fromDegrees(r.lon, r.lat)
        const position = Cartesian3.fromRadians(carto.longitude, carto.latitude, scene.globe.getHeight(carto) ?? 0, MARS)
        if (Cartesian3.dot(position, camPos) <= R2 * 0.99) continue
        const p = SceneTransforms.worldToWindowCoordinates(scene, position, scratch)
        if (!p) continue
        placed.push({ x0: p.x - r.w / 2, x1: p.x + r.w / 2, y0: p.y + r.dy - r.h / 2, y1: p.y + r.dy + r.h / 2 })
      }
      let shown = 0
      for (const it of items) {          // sites, then largest first
        let visible = false
        const eligible = it.site
          ? showSitesRef.current && h <= SITE_MAX_HEIGHT
          : showRef.current && shown < MAX_LABELS && it.dEff >= minKm
        if (eligible && Cartesian3.dot(it.pos, camPos) > R2) {
          // Sit the label on the rendered (exaggerated) terrain, then measure where it lands.
          const gh = scene.globe.getHeight(it.carto) ?? 0
          if (Math.abs(gh - it.groundH) > 0.5) {
            it.groundH = gh
            it.label.position = Cartesian3.fromRadians(it.carto.longitude, it.carto.latitude, gh, MARS)
          }
          const p = it.label.computeScreenSpacePosition(scene, scratch)
          if (p && p.x - it.w / 2 > vx0 && p.y - it.h / 2 > vy0 && p.x + it.w / 2 < vx1 && p.y + it.h / 2 < vy1 &&
              !(is3d && h < 1_000_000 && occluded(it))) {
            const cy = p.y
            const box = { x0: p.x - it.w / 2 - PAD, x1: p.x + it.w / 2 + PAD, y0: cy - it.h / 2 - PAD, y1: cy + it.h / 2 + PAD }
            if (!placed.some(b => overlaps(b, box))) {
              placed.push(box)
              visible = true
              if (!it.site) shown++
            }
          }
        }
        it.label.show = visible
      }
    }
    updateRef.current = () => { dirty = true }

    // Wait for the display font so labels are rasterised with it (it is bundled locally).
    document.fonts.load(TIERS[1].font).catch(() => undefined).finally(() => {
      if (disposed || viewer.isDestroyed()) return
      collection = viewer.scene.primitives.add(new LabelCollection({ scene: viewer.scene }))
      const halo = Color.fromCssColorString('#0a0e1a')
      const siteFill = Color.fromCssColorString('#e8f0ff')
      for (const s of sites) {
        const pos = Cartesian3.fromDegrees(s.lon, s.lat, 0, MARS)
        const carto = Cartographic.fromDegrees(s.lon, s.lat)
        const label = collection!.add({
          position: pos, text: s.text, font: SITE_FONT, fillColor: siteFill,
          outlineColor: halo, outlineWidth: 4, style: LabelStyle.FILL_AND_OUTLINE,
          horizontalOrigin: HorizontalOrigin.CENTER, verticalOrigin: VerticalOrigin.CENTER,
          pixelOffset: new Cartesian2(0, SITE_DY), disableDepthTestDistance: Number.POSITIVE_INFINITY, show: false,
        })
        items.push({ site: true, label, fill: siteFill, halo, pos, carto, groundH: 0, w: s.text.length * 13 * 0.56 + 6, h: 17, dy: SITE_DY, dEff: Infinity })
      }
      for (const f of GAZETTEER.features) {
        if (exclude(f)) continue
        const t = tierFor(f.d)
        const text = t.upper ? f.n.toUpperCase() : f.n
        const pos = Cartesian3.fromDegrees(f.lon, f.lat, 0, MARS)
        const carto = Cartographic.fromDegrees(f.lon, f.lat)
        const label = collection!.add({
          position: pos, text, font: t.font, fillColor: t.color,
          outlineColor: halo, outlineWidth: 3,
          style: LabelStyle.FILL_AND_OUTLINE,
          horizontalOrigin: HorizontalOrigin.CENTER, verticalOrigin: VerticalOrigin.CENTER,
          // Depth is handled by our own horizon test (labels sit exactly on the surface).
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          show: false,
        })
        items.push({ site: false, label, fill: t.color, halo, pos, carto, groundH: 0, w: text.length * t.px * t.widthFactor + 6, h: t.px + 4, dy: 0, dEff: Math.max(f.d, MIN_DIAMETER_KM) })
      }
      // Re-declutter when the camera moves (throttled to ~8 Hz) and after it stops.
      // Terrain finished loading somewhere → ground heights may have changed.
      const offTiles = viewer.scene.globe.tileLoadProgressEvent.addEventListener((queued: number) => { if (queued === 0) dirty = true })
      let lastEx = viewer.scene.verticalExaggeration
      const offRender = viewer.scene.postRender.addEventListener(() => {
        const cam = viewer.camera
        if (viewer.scene.verticalExaggeration !== lastEx) { lastEx = viewer.scene.verticalExaggeration; dirty = true }
        if (!Cartesian3.equalsEpsilon(cam.positionWC, lastCam, 0, 1) ||
            !Cartesian3.equalsEpsilon(cam.directionWC, lastDir, 1e-6)) {
          Cartesian3.clone(cam.positionWC, lastCam)
          Cartesian3.clone(cam.directionWC, lastDir)
          dirty = true
        }
        if (dirty && performance.now() - lastRun > 120) update()
      })
      removeListener = () => { offTiles(); offRender() }
      applyAlpha()
      update()
    })

    return () => {
      disposed = true
      removeListener?.()
      if (collection && !viewer.isDestroyed()) viewer.scene.primitives.remove(collection)
    }
  }, [viewer, terrainKey, exclude, sites])

  // Toggle / reserved changes → re-run on the next frame.
  useEffect(() => { updateRef.current() }, [show, showSites, reserved])
  // Opacity sliders → recolour the existing labels in place.
  useEffect(() => { applyAlphaRef.current() }, [labelAlpha, siteAlpha])
}
