import { create } from 'zustand'

export type HiriseStyle = 'hillshade' | 'elevation' | 'slope'

/** Top-bar tab: the Gale study area (route planning) or the whole planet (landing sites). */
export type MapView = 'study' | 'mars'

/** Every toggleable map layer, for per-layer opacity. */
export type LayerId =
  | 'hirise' | 'ortho' | 'gapFill' | 'footprint' | 'route'
  | 'sites' | 'minerals' | 'labels' | 'geology' | 'traverse'

const FULL: Record<LayerId, number> = {
  hirise: 1, ortho: 1, gapFill: 1, footprint: 1, route: 1,
  sites: 1, minerals: 1, labels: 1, geology: 1, traverse: 1,
}

interface LayerState {
  showHiRISE: boolean
  showGapFill: boolean
  showTraverse: boolean
  showRoute: boolean
  showSites: boolean
  showLabels: boolean
  showFootprint: boolean
  showMinerals: boolean
  showGeology: boolean
  /** HiRISE ortho photo mosaic (~1 m/px). Off by default. Exclusive with showHiRISE: the
   *  draped hillshade entity always renders above imagery layers and would hide the photo. */
  showOrtho: boolean
  hiriseStyle: HiriseStyle
  /** Vertical exaggeration of the 3D terrain (1–5×). */
  exaggeration: number
  /** Per-layer opacity, 0–1 (default 1). Multiplies each layer's own styling alpha. */
  opacity: Record<LayerId, number>
  view: MapView
  toggleHiRISE: () => void
  toggleGapFill: () => void
  toggleTraverse: () => void
  toggleRoute: () => void
  toggleSites: () => void
  toggleLabels: () => void
  toggleFootprint: () => void
  toggleMinerals: () => void
  toggleGeology: () => void
  toggleOrtho: () => void
  setHiriseStyle: (s: HiriseStyle) => void
  setExaggeration: (v: number) => void
  setOpacity: (id: LayerId, v: number) => void
  setView: (v: MapView) => void
}

export const useLayerStore = create<LayerState>(set => ({
  showHiRISE: true,
  showGapFill: true,
  // NASA's proposed Curiosity path: a reference layer, on by default.
  showTraverse: true,
  showRoute: true,
  showSites: true,
  showLabels: true,
  showFootprint: true,
  showMinerals: false,
  showGeology: false,
  showOrtho: false,
  hiriseStyle: 'hillshade',
  exaggeration: 3,
  opacity: FULL,
  view: 'study',
  toggleHiRISE: () => set(s => ({ showHiRISE: !s.showHiRISE, showOrtho: s.showHiRISE ? s.showOrtho : false })),
  toggleGapFill: () => set(s => ({ showGapFill: !s.showGapFill })),
  toggleTraverse: () => set(s => ({ showTraverse: !s.showTraverse })),
  toggleRoute: () => set(s => ({ showRoute: !s.showRoute })),
  toggleSites: () => set(s => ({ showSites: !s.showSites })),
  toggleLabels: () => set(s => ({ showLabels: !s.showLabels })),
  toggleFootprint: () => set(s => ({ showFootprint: !s.showFootprint })),
  toggleMinerals: () => set(s => ({ showMinerals: !s.showMinerals })),
  toggleGeology: () => set(s => ({ showGeology: !s.showGeology })),
  toggleOrtho: () => set(s => ({ showOrtho: !s.showOrtho, showHiRISE: s.showOrtho ? s.showHiRISE : false })),
  setHiriseStyle: hiriseStyle => set({ hiriseStyle }),
  setExaggeration: exaggeration => set({ exaggeration: Math.min(5, Math.max(1, exaggeration)) }),
  setView: view => set({ view }),
  setOpacity: (id, v) => set(s => ({ opacity: { ...s.opacity, [id]: Math.min(1, Math.max(0, v)) } })),
}))
