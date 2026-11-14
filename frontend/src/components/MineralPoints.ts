// Aqueous-mineral detection sites (Ehlmann & Edwards 2014; CRISM / OMEGA / THEMIS) as a
// point layer on the globe. Data: GET /api/layers/minerals (bundled by the backend).
//
// Points are placed on the 3D surface using each site's MOLA height, exaggerated the
// same way as the terrain: h' = (h − ref)·ex + ref, plus a small lift. Points closer to the
// camera than the horizon are always on the visible side of the planet, so depth testing is
// disabled up to the horizon distance (otherwise coarse distant terrain half-buries them);
// beyond it, depth testing hides points on the far side.
import { useEffect, useRef } from 'react'
import {
  Cartesian3, Color, NearFarScalar, PointPrimitiveCollection, type PointPrimitive,
  type Viewer as CesiumViewer,
} from 'cesium'
import type { MineralPoint, MineralsLayer } from '../api/cosmic'
import { MARS, MARS_RADIUS } from '../mars'

/** Distance from the camera to its horizon on the Mars sphere, slightly reduced. */
const horizonDistance = (viewer: CesiumViewer) => {
  const h = Math.max(viewer.camera.positionCartographic.height, 1000)
  return 0.97 * Math.sqrt(h * (2 * MARS_RADIUS + h))
}

const LIFT_M = 60                 // above the rendered surface

/** Picked primitive id for a mineral point. */
export interface MineralPick { mineral: MineralPoint; label: string; color: string }

export function useMineralPoints(
  viewer: CesiumViewer | undefined,
  layer: MineralsLayer | null,
  show: boolean,
  exaggeration: number,
  referenceHeight: number,
  /** Opacity slider, 0–1. */
  opacity = 1,
) {
  const colRef = useRef<PointPrimitiveCollection | null>(null)
  const ptsRef = useRef<{ prim: PointPrimitive; p: MineralPoint; color: Color }[]>([])
  const outline = useRef(Color.fromCssColorString('#0a0e1a')).current
  const opacityRef = useRef(opacity)
  opacityRef.current = opacity

  // Build the collection once per data set.
  useEffect(() => {
    if (!viewer || !layer?.available || !layer.points?.length) return
    const legend = new Map((layer.legend ?? []).map(l => [l.class, l]))
    const col = viewer.scene.primitives.add(new PointPrimitiveCollection()) as PointPrimitiveCollection
    const a = opacityRef.current
    // Slightly larger when close, never smaller than 6 px at globe scale.
    const scale = new NearFarScalar(5e4, 1.4, 8e6, 0.75)
    ptsRef.current = layer.points.map(p => {
      const l = legend.get(p.c)
      const color = Color.fromCssColorString(l?.color ?? '#cccccc')
      const prim = col.add({
        position: Cartesian3.fromDegrees(p.lon, p.lat, 0, MARS),
        color: color.withAlpha(a), pixelSize: 8, outlineColor: outline.withAlpha(a), outlineWidth: 1.5,
        scaleByDistance: scale, disableDepthTestDistance: horizonDistance(viewer),
        id: { mineral: p, label: l?.label ?? p.c, color: l?.color ?? '#cccccc' } satisfies MineralPick,
      })
      return { prim, p, color }
    })
    colRef.current = col
    // Keep the no-depth distance equal to the horizon distance as the camera moves.
    let current = horizonDistance(viewer)
    const refresh = () => {
      const d = horizonDistance(viewer)
      if (Math.abs(d - current) / current < 0.1) return
      current = d
      for (const { prim } of ptsRef.current) prim.disableDepthTestDistance = d
    }
    viewer.camera.percentageChanged = Math.min(viewer.camera.percentageChanged, 0.2)
    const offChanged = viewer.camera.changed.addEventListener(refresh)
    const offEnd = viewer.camera.moveEnd.addEventListener(refresh)
    return () => {
      offChanged(); offEnd()
      if (!viewer.isDestroyed()) viewer.scene.primitives.remove(col)
      colRef.current = null
      ptsRef.current = []
    }
  }, [viewer, layer])

  // Show / hide. (viewer is a dependency: the collection may be built after the data arrives.)
  useEffect(() => { if (colRef.current) colRef.current.show = show }, [viewer, show, layer])

  // Opacity slider.
  useEffect(() => {
    for (const { prim, color } of ptsRef.current) {
      prim.color = color.withAlpha(opacity)
      prim.outlineColor = outline.withAlpha(opacity)
    }
  }, [viewer, layer, opacity, outline])

  // Heights follow the terrain exaggeration.
  useEffect(() => {
    for (const { prim, p } of ptsRef.current) {
      const h = p.h ?? referenceHeight
      prim.position = Cartesian3.fromDegrees(p.lon, p.lat, (h - referenceHeight) * exaggeration + referenceHeight + LIFT_M, MARS)
    }
  }, [viewer, layer, exaggeration, referenceHeight])
}
