// Zoom aids for the map: a metric scale bar, and — over the HiRISE photo layer — a zoom stop at the
// photo's real resolution plus a small "Max HiRISE detail · X m/px" chip when you are there.
//
// Zoom stop: the camera may come close enough for one photo pixel to cover MAX_MAGNIFICATION CSS
// pixels, no closer (beyond that the image is only magnified, not more detailed). The resolution is
// the one under the centre of the view: the sharp mosaic where it has data (the backend's
// detail_grid), the 1 m fallback elsewhere. Cesium's own zoom inertia eases into the stop; if the
// camera is already closer (the photo layer was just switched on, or you panned onto it from
// lower ground) it is lifted to the stop with a short eased flight.
//
// Nothing here changes the imagery itself: no sharpening, no upscaling.
import { useEffect, useRef, useState } from 'react'
import {
  Cartesian2, Cartesian3, Cartographic, EasingFunction, HeadingPitchRange, BoundingSphere,
  Math as CesiumMath, type PerspectiveFrustum, type Viewer as CesiumViewer,
} from 'cesium'
import type { OrthoInfo } from '../api/cosmic'
import { MARS } from '../mars'

const MAX_MAGNIFICATION = 1.5   // CSS px per photo pixel at the zoom stop
const DEFAULT_MIN_ZOOM = 1      // Cesium's default minimumZoomDistance (m)
const AT_LIMIT = 1.2            // within 20 % of the stop counts as "at max detail"
const SCALE_MAX_PX = 120        // longest scale bar
const NICE = [1, 2, 5]

interface Scale { px: number; label: string }

/** Ground point under a canvas position (terrain), or null when it misses the planet. */
function groundAt(v: CesiumViewer, x: number, y: number): Cartesian3 | null {
  const ray = v.camera.getPickRay(new Cartesian2(x, y))
  return (ray && v.scene.globe.pick(ray, v.scene)) ?? null
}

/** Photo resolution (m/px) at lon/lat, or null outside the photo layer. */
function photoResAt(o: OrthoInfo, lon: number, lat: number): number | null {
  if (!o.available || o.west === undefined || o.east === undefined || o.south === undefined || o.north === undefined) return null
  if (lon < o.west || lon > o.east || lat < o.south || lat > o.north) return null
  const res = o.resolution_m ?? 1
  const g = o.detail_grid
  if (!g || !o.fallback) return res
  const c = Math.min(g.cols - 1, Math.floor((lon - o.west) / (o.east - o.west) * g.cols))
  const r = Math.min(g.rows - 1, Math.floor((o.north - lat) / (o.north - o.south) * g.rows))
  return g.cells[r]?.[c] === '1' ? res : o.fallback.resolution_m
}

function niceScale(mPerPx: number): Scale | null {
  if (!Number.isFinite(mPerPx) || mPerPx <= 0) return null
  const maxM = mPerPx * SCALE_MAX_PX
  const p = 10 ** Math.floor(Math.log10(maxM))
  const m = [...NICE].reverse().map(n => n * p).find(n => n <= maxM) ?? p
  return { px: m / mPerPx, label: m >= 1000 ? `${m / 1000} km` : `${m} m` }
}

export default function ZoomAids({ viewer, ortho, showOrtho, showScale }: {
  viewer?: CesiumViewer; ortho: OrthoInfo | null; showOrtho: boolean; showScale: boolean
}) {
  const [scale, setScale] = useState<Scale | null>(null)
  const [maxDetail, setMaxDetail] = useState<number | null>(null)
  const state = useRef({ ortho, showOrtho })
  state.current = { ortho, showOrtho }
  const force = useRef(true)          // re-evaluate on the next frame even if the camera is still

  useEffect(() => {
    if (!viewer) return
    const ctrl = viewer.scene.screenSpaceCameraController
    let last = 0, lifting = false
    const lastPos = new Cartesian3(), lastDir = new Cartesian3()

    const update = (forced = false) => {
      if (viewer.isDestroyed()) return
      const cam = viewer.camera
      if (!forced && Cartesian3.equalsEpsilon(cam.positionWC, lastPos, 0, 0.5) &&
          Cartesian3.equalsEpsilon(cam.directionWC, lastDir, 1e-7)) return
      Cartesian3.clone(cam.positionWC, lastPos); Cartesian3.clone(cam.directionWC, lastDir)
      const canvas = viewer.scene.canvas
      const w = canvas.clientWidth, h = canvas.clientHeight
      const centre = groundAt(viewer, w / 2, h / 2)
      // Scale: ground distance between two points 100 CSS px apart at the centre of the view.
      const a = groundAt(viewer, w / 2 - 50, h / 2), b = groundAt(viewer, w / 2 + 50, h / 2)
      setScale(a && b ? niceScale(Cartesian3.distance(a, b) / 100) : null)

      // Zoom stop over the photo layer.
      const { ortho: o, showOrtho: on } = state.current
      let limit: number | null = null, res: number | null = null
      if (on && o && centre) {
        const c = Cartographic.fromCartesian(centre, MARS)
        res = photoResAt(o, CesiumMath.toDegrees(c.longitude), CesiumMath.toDegrees(c.latitude))
        if (res) {
          const fov = (cam.frustum as PerspectiveFrustum).fov ?? CesiumMath.PI_OVER_THREE
          // Cesium's fov spans the canvas's larger dimension: metres per CSS px = 2·d·tan(fov/2)/max(w,h).
          limit = (res / MAX_MAGNIFICATION) * Math.max(w, h) / (2 * Math.tan(fov / 2))
        }
      }
      ctrl.minimumZoomDistance = limit ?? DEFAULT_MIN_ZOOM
      const dist = centre ? Cartesian3.distance(cam.positionWC, centre) : Infinity
      setMaxDetail(limit && dist <= limit * AT_LIMIT ? res : null)
      // Already closer than the stop (layer just switched on, or panned in low): lift gently.
      if (limit && centre && dist < limit * 0.95 && !lifting) {
        lifting = true
        cam.flyToBoundingSphere(new BoundingSphere(centre, 0), {
          offset: new HeadingPitchRange(cam.heading, cam.pitch, limit),
          duration: 0.8, easingFunction: EasingFunction.QUADRATIC_OUT,
          complete: () => { lifting = false; force.current = true }, cancel: () => { lifting = false },
        })
      }
    }

    const off = viewer.scene.postRender.addEventListener(() => {
      const now = performance.now()
      if (now - last > 150) { last = now; const f = force.current; force.current = false; update(f) }
    })
    // Terrain under the view finished loading: ground picks (scale, distance) may have changed.
    const offTiles = viewer.scene.globe.tileLoadProgressEvent.addEventListener((q: number) => { if (q === 0) force.current = true })
    return () => {
      off(); offTiles()
      if (!viewer.isDestroyed()) ctrl.minimumZoomDistance = DEFAULT_MIN_ZOOM
    }
  }, [viewer])

  // Toggling the photo layer (or new photo info) re-evaluates the stop on the next frame.
  useEffect(() => { force.current = true }, [ortho, showOrtho])

  return (
    <>
      {showScale && scale && (
        <div className="map-scale" aria-label={`Map scale: ${scale.label}`}>
          <span className="map-scale-bar" style={{ width: `${Math.round(scale.px)}px` }} />
          <span className="map-scale-label">{scale.label}</span>
        </div>
      )}
      <div className={`max-detail glass ${maxDetail ? 'on' : ''}`} role="status" aria-live="polite">
        {maxDetail ? `Max HiRISE detail · ${maxDetail % 1 ? maxDetail.toFixed(2).replace(/0$/, '') : maxDetail} m/px` : ''}
      </div>
    </>
  )
}
