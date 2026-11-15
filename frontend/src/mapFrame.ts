// Full-bleed map with content centred in the UNCOVERED area.
//
// The map fills the whole window behind the glass panels (sidebar on the left, the dock with
// the hover-info bar and the elevation panel at the bottom). To centre views in the part of
// the map that is actually visible, the Cesium viewer element is sized and positioned so that
// ITS centre is the centre of the uncovered area; it overhangs the window edges and the window
// clips it. Cesium therefore centres and frames everything on the visible area by itself, and
// picking stays exact because this is plain layout (no CSS transform on the canvas).
//
// Why not PerspectiveFrustum.xOffset / yOffset: Cesium's pick rays ignore them
// (Camera.getPickRayPerspective uses only fovy, aspect and near), and the renderer replaces
// `near` per frame (frustum.near = frustumCommands.near) while the offsets are in near-plane
// units, so the shift would drift with zoom and clicks / hover would land in the wrong place.
//
// One measurement drives everything, published as CSS variables on <html>:
//   --vis-left  width covered by the sidebar     --dock-h  height covered by the bottom dock
//   --map-x / --map-y / --map-w / --map-h        the viewer element's box (see .cesium-host)
import { Math as CesiumMath, Rectangle, type PerspectiveFrustum, type Viewer as CesiumViewer } from 'cesium'

export interface MapFrame {
  /** Window-sized map region (the .globe element), px. */
  width: number
  height: number
  /** Uncovered area inside it: x from visLeft to width, y from 0 to visBottom. */
  visLeft: number
  visBottom: number
  /** Viewer element box, relative to the map region. */
  mapX: number
  mapY: number
  mapW: number
  mapH: number
}

let frame: MapFrame | null = null

/** Measure the panels and update the viewer box + CSS variables. Returns the new frame. */
export function measureMapFrame(): MapFrame | null {
  const globe = document.querySelector<HTMLElement>('.globe')
  if (!globe) return frame
  const g = globe.getBoundingClientRect()
  const width = g.width, height = g.height
  let visLeft = 0, visBottom = height
  // Panels float over the map only in the desktop layout (on small screens they stack below it).
  const side = document.querySelector<HTMLElement>('.sidebar')
  if (side && getComputedStyle(side).position === 'absolute') {
    visLeft = Math.min(width * 0.6, Math.max(0, side.getBoundingClientRect().right - g.left))
    const dock = document.querySelector<HTMLElement>('.dock')
    const d = dock?.getBoundingClientRect()
    if (d && d.height > 0) visBottom = Math.max(height * 0.3, d.top - g.top)
  }
  // Viewer box centred on the uncovered area's centre, large enough to cover the whole window.
  const cx = (visLeft + width) / 2, cy = visBottom / 2
  const hw = Math.max(cx, width - cx), hh = Math.max(cy, height - cy)
  frame = { width, height, visLeft, visBottom, mapX: cx - hw, mapY: cy - hh, mapW: 2 * hw, mapH: 2 * hh }
  const s = document.documentElement.style
  s.setProperty('--vis-left', `${Math.round(visLeft)}px`)
  s.setProperty('--dock-h', `${Math.round(height - visBottom)}px`)
  s.setProperty('--map-x', `${Math.round(frame.mapX)}px`)
  s.setProperty('--map-y', `${Math.round(frame.mapY)}px`)
  s.setProperty('--map-w', `${Math.round(frame.mapW)}px`)
  s.setProperty('--map-h', `${Math.round(frame.mapH)}px`)
  return frame
}

/** Ratio of the viewer box to the uncovered area (≥ 1 in each direction). */
function overscan(f: MapFrame) {
  const visW = Math.max(1, f.width - f.visLeft), visH = Math.max(1, f.visBottom)
  return { sx: f.mapW / visW, sy: f.mapH / visH }
}

/**
 * The rectangle to give camera.flyTo so that `rect` fits the UNCOVERED area: Cesium fits a
 * rectangle to the whole viewer box, so it is grown by the box/visible-area ratio about its centre.
 */
export function fitToVisible(rect: Rectangle): Rectangle {
  const f = frame ?? measureMapFrame()
  if (!f) return rect
  const { sx, sy } = overscan(f)
  const c = Rectangle.center(rect)
  const hw = (Rectangle.computeWidth(rect) / 2) * sx
  const hh = (Rectangle.computeHeight(rect) / 2) * sy
  const lim = CesiumMath.PI_OVER_TWO - 1e-6
  return new Rectangle(c.longitude - hw, Math.max(-lim, c.latitude - hh), c.longitude + hw, Math.min(lim, c.latitude + hh))
}

/** Half-extent of the uncovered area as tangents of the view angle (x, y), for framing the globe. */
export function visibleTangents(v: CesiumViewer): { tx: number; ty: number } {
  const f = frame ?? measureMapFrame()
  const canvas = v.scene.canvas
  const cw = canvas.clientWidth, ch = canvas.clientHeight
  const fov = (v.camera.frustum as PerspectiveFrustum).fov ?? CesiumMath.PI_OVER_THREE
  // Cesium's fov is the horizontal angle on landscape canvases, the vertical one otherwise.
  const perPx = Math.tan(fov / 2) / (Math.max(cw, ch) / 2)
  const visW = f ? f.width - f.visLeft : cw, visH = f ? f.visBottom : ch
  return { tx: (visW / 2) * perPx, ty: (visH / 2) * perPx }
}
