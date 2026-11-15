// One label style for everything drawn on the globe: IAU place names, the Gale Crater marker,
// NASA landing sites, science sites, Curiosity waypoints, mineral detections and the routable-area tag.
//
// White semi-bold text with a black outline reads on every basemap (dark MOLA blues, bright HiRISE
// hillshade, the orange Viking mosaic). Small labels that belong to a marker also get a subtle dark
// rounded background and sit beside the marker (pixelOffset), never on top of it.
//
// Visibility per category: `maxHeight` is the camera height (m) below which a category is shown
// (also set as the label's distanceDisplayCondition); scaleByDistance / translucencyByDistance soften
// labels as they approach that limit. The declutter in components/MarsLabels.ts decides overlaps.
import { Cartesian2, Color, DistanceDisplayCondition, LabelStyle, NearFarScalar } from 'cesium'

export const LABEL_FONT_FAMILY = "'Space Grotesk', 'Segoe UI', system-ui, sans-serif"

export type LabelCategory =
  | 'region' | 'feature' | 'minor'                       // IAU gazetteer, by size
  | 'gale' | 'landing' | 'site' | 'waypoint' | 'mineral' // markers
  | 'area'                                               // "ROUTABLE AREA" tag

export interface CategoryStyle {
  px: number
  weight: 600 | 700
  upper?: boolean
  outlineWidth: number
  /** Dark rounded background for small labels next to a marker. */
  background?: boolean
  /** Camera height (m) up to which the category is shown. */
  maxHeight: number
  /** Gap (px) between the marker anchor and the label, on the marker's right (or left). */
  gap?: number
  /** Vertical offset (px) of the label centre from the anchor (pins are anchored at their tip). */
  dy?: number
  fill?: Color
}

const WHITE = Color.WHITE
export const LABEL_OUTLINE = Color.BLACK
export const LABEL_BACKGROUND = Color.fromCssColorString('#0a0e1a').withAlpha(0.66)
export const LABEL_PADDING = new Cartesian2(6, 3)

export const CATEGORY: Record<LabelCategory, CategoryStyle> = {
  region:   { px: 16, weight: 700, upper: true, outlineWidth: 4, maxHeight: Number.POSITIVE_INFINITY },
  feature:  { px: 14, weight: 600, outlineWidth: 3.5, maxHeight: 8_000_000 },
  minor:    { px: 13, weight: 600, outlineWidth: 3, maxHeight: 1_500_000 },
  gale:     { px: 16, weight: 700, outlineWidth: 4, maxHeight: Number.POSITIVE_INFINITY },
  landing:  { px: 14, weight: 600, outlineWidth: 3, background: true, maxHeight: Number.POSITIVE_INFINITY, gap: 14 },
  site:     { px: 14, weight: 600, outlineWidth: 3, background: true, maxHeight: 400_000, gap: 16, dy: -20 },
  waypoint: { px: 13, weight: 600, outlineWidth: 3, background: true, maxHeight: 100_000, gap: 12 },
  mineral:  { px: 13, weight: 600, outlineWidth: 3, background: true, maxHeight: 250_000, gap: 11 },
  area:     { px: 12, weight: 600, upper: true, outlineWidth: 3, maxHeight: 250_000,
              fill: Color.fromCssColorString('#4a9eff') },
}

export const fontFor = (c: LabelCategory) => `${CATEGORY[c].weight} ${CATEGORY[c].px}px ${LABEL_FONT_FAMILY}`

/** Size falls to 85 % and opacity to 55 % over the last 40 % of the category's range. */
function ramps(max: number) {
  if (!Number.isFinite(max)) {
    return { scale: new NearFarScalar(2e6, 1.0, 2e7, 0.85), fade: undefined }
  }
  return {
    scale: new NearFarScalar(max * 0.6, 1.0, max, 0.85),
    fade: new NearFarScalar(max * 0.6, 1.0, max, 0.55),
  }
}

const RAMPS = Object.fromEntries(
  (Object.keys(CATEGORY) as LabelCategory[]).map(c => [c, ramps(CATEGORY[c].maxHeight)]),
) as Record<LabelCategory, ReturnType<typeof ramps>>

/** Options for a Cesium label (LabelCollection.add or <LabelGraphics>) of one category. */
export function labelOptions(c: LabelCategory) {
  const s = CATEGORY[c]
  const { scale, fade } = RAMPS[c]
  return {
    font: fontFor(c),
    fillColor: s.fill ?? WHITE,
    outlineColor: LABEL_OUTLINE,
    outlineWidth: s.outlineWidth,
    style: LabelStyle.FILL_AND_OUTLINE,
    showBackground: !!s.background,
    backgroundColor: LABEL_BACKGROUND,
    backgroundPadding: LABEL_PADDING,
    distanceDisplayCondition: new DistanceDisplayCondition(0, s.maxHeight),
    scaleByDistance: scale,
    translucencyByDistance: fade,
    // Never hidden inside terrain; the declutter hides labels on the far side of the planet.
    disableDepthTestDistance: Number.POSITIVE_INFINITY,
  }
}

/** The scale a label of this category gets at `distance` m (mirrors scaleByDistance). */
export function scaleAt(c: LabelCategory, distance: number) {
  const s = RAMPS[c].scale
  if (distance <= s.near) return s.nearValue
  if (distance >= s.far) return s.farValue
  const t = (distance - s.near) / (s.far - s.near)
  return s.nearValue + t * (s.farValue - s.nearValue)
}

const measureCtx = document.createElement('canvas').getContext('2d')!

/** On-screen box (px, at scale 1) of a label's text including outline and background padding. */
export function measureLabel(c: LabelCategory, text: string) {
  const s = CATEGORY[c]
  measureCtx.font = fontFor(c)
  const pad = s.background ? LABEL_PADDING : { x: 0, y: 0 }
  return {
    // +6 % and +2 px: Cesium's own glyph box comes out a little wider than the canvas measurement.
    w: Math.ceil(measureCtx.measureText(text).width * 1.06 + 2 + s.outlineWidth + 2 * pad.x),
    h: Math.ceil(s.px * 1.3 + 2 * pad.y),
  }
}
