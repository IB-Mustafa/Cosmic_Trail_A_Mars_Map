import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Cartographic, Math as CesiumMath, ScreenSpaceEventHandler, ScreenSpaceEventType,
  type Cartesian2, type Viewer as CesiumViewer,
} from 'cesium'
import { getLookup, type GeologicUnitProps, type GeologicUnits, type LonLat, type Lookup } from '../api/cosmic'
import { MARS } from '../mars'
import { useLayerStore } from '../store/layerStore'
import { useRouteStore } from '../store/routeStore'

const fmtLat = (v: number) => `${Math.abs(v).toFixed(4)}°${v < 0 ? 'S' : 'N'}`
const fmtLon = (v: number) => `${Math.abs(v).toFixed(4)}°${v < 0 ? 'W' : 'E'}`
const fmtM = (v: number) => `${v.toLocaleString('en-US', { maximumFractionDigits: 1, minimumFractionDigits: 1 })} m`

/** Ray-casting point-in-polygon on a lon/lat ring (small areas: planar is fine). */
function inRing(p: LonLat, ring: [number, number][]) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j]
    if ((yi > p.lat) !== (yj > p.lat) && p.lon < ((xj - xi) * (p.lat - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

function unitAt(geology: GeologicUnits | null, p: LonLat): GeologicUnitProps | null {
  for (const f of geology?.features ?? []) {
    const [outer, ...holes] = f.geometry.coordinates
    if (inRing(p, outer) && !holes.some(h => inRing(p, h))) return f.properties
  }
  return null
}

/** Terrain surface under a screen position (exaggerated terrain → pick the globe, not the ellipsoid). */
function pickLonLat(v: CesiumViewer, pos: Cartesian2): LonLat | null {
  const ray = v.camera.getPickRay(pos)
  const cart = (ray && v.scene.globe.pick(ray, v.scene)) ?? v.camera.pickEllipsoid(pos, MARS)
  if (!cart) return null
  const c = Cartographic.fromCartesian(cart, MARS)
  return { lon: CesiumMath.toDegrees(c.longitude), lat: CesiumMath.toDegrees(c.latitude) }
}

/**
 * Bottom inspector bar: cursor lon/lat and the value of every visible layer under it.
 * Terrain values come from the backend lookup (the same 5 m grid the router uses); outside
 * that grid it shows the coarse MOLA height of the 3D globe, labelled as such. Requests are
 * throttled to one in flight, always for the latest cursor position.
 */
export default function Inspector({ viewer }: { viewer?: CesiumViewer }) {
  const dataset = useRouteStore(s => s.dataset)
  const geology = useRouteStore(s => s.geology)
  const l = useLayerStore()
  const [pos, setPos] = useState<LonLat | null>(null)
  const [look, setLook] = useState<Lookup | null>(null)

  // Cursor tracking (mouse move; tap/click on touch screens).
  useEffect(() => {
    if (!viewer) return
    const h = new ScreenSpaceEventHandler(viewer.scene.canvas)
    const update = (p: Cartesian2) => setPos(pickLonLat(viewer, p))
    h.setInputAction((m: { endPosition: Cartesian2 }) => update(m.endPosition), ScreenSpaceEventType.MOUSE_MOVE)
    h.setInputAction((m: { position: Cartesian2 }) => update(m.position), ScreenSpaceEventType.LEFT_CLICK)
    const leave = () => setPos(null)
    viewer.scene.canvas.addEventListener('mouseleave', leave)
    return () => {
      viewer.scene.canvas.removeEventListener('mouseleave', leave)
      h.destroy()
    }
  }, [viewer])

  // Backend lookup, one request in flight, always for the newest position.
  const wanted = useRef<LonLat | null>(null)
  const busy = useRef(false)
  const pump = useCallback(() => {
    if (busy.current || !wanted.current || !dataset) return
    const p = wanted.current
    wanted.current = null
    busy.current = true
    getLookup(dataset.id, { lon: +p.lon.toFixed(6), lat: +p.lat.toFixed(6) })
      .then(setLook)
      .catch(() => setLook(null))
      .finally(() => { busy.current = false; setTimeout(pump, 40) })
  }, [dataset])
  useEffect(() => {
    if (pos) { wanted.current = pos; pump() }
  }, [pos, pump])

  if (!pos) {
    return (
      <div className="inspector glass" data-occludes aria-live="off">
        <span className="hint">Move the cursor over Mars to inspect elevation, slope and data source</span>
      </div>
    )
  }

  const inGrid = !!look?.in_study_area
  const elev = look?.elevation_m
  const src = look?.elevation_source
  const isFill = !!src && src !== 'HiRISE'
  const unit = l.showGeology ? unitAt(geology, pos) : null
  const status = look?.status

  return (
    <div className="inspector glass" data-occludes aria-live="off">
      <span className="coord"><b>{fmtLat(pos.lat)}</b> <b>{fmtLon(pos.lon)}</b></span>
      {look && (inGrid && elev != null ? (
        <span title="Elevation from the 5 m analysis grid (areoid-referenced), same values the router uses">
          Elevation <b>{fmtM(elev)}</b>
        </span>
      ) : look.context_elevation_m != null ? (
        <span title={`Coarse context height outside the routing grid: ${look.context_source ?? 'MOLA'}`}>
          Elevation <b>{fmtM(look.context_elevation_m)}</b> <small>MOLA</small>
        </span>
      ) : (
        <span>Elevation <b>—</b></span>
      ))}
      {inGrid && l.showHiRISE && (
        <span title="Slope of the 5 m analysis grid">
          Slope <b>{look?.slope_deg != null ? `${look.slope_deg.toFixed(1)}°` : '—'}</b>
        </span>
      )}
      {inGrid && src && l.showHiRISE && (
        <span title="Where this cell's elevation comes from">
          Source <b className={isFill ? 'src-fill' : 'src-hirise'}>{isFill ? src.replace(' (gap fill)', '') + ' · gap fill' : 'HiRISE DTM'}</b>
        </span>
      )}
      {l.showFootprint && look && (
        <span title="Whether the router can use this point">
          {inGrid
            ? (status === 'ok' ? <b className="ok">Routable</b> : <b className="warn">{status === 'nodata' ? 'No data' : 'Slope unknown'}</b>)
            : <span className="muted">Outside routable area</span>}
        </span>
      )}
      {unit && (
        <span title={unit.description}>Unit <b>{unit.unit}</b> <small>{unit.name}</small></span>
      )}
    </div>
  )
}
