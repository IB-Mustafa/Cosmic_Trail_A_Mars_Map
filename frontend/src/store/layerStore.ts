import { create } from 'zustand'

export type HiriseStyle = 'hillshade' | 'elevation' | 'slope'

/** Top-bar tab: the Gale study area (route planning) or the whole planet (landing sites). */
export type MapView = 'study' | 'mars'

/** Every toggleable map layer. */
export type LayerId =
  | 'hirise' | 'ortho' | 'footprint' | 'route'
  | 'sites' | 'minerals' | 'labels' | 'geology' | 'traverse'

/** All layers render at full opacity (the per-layer sliders were removed). */
const FULL: Readonly<Record<LayerId, number>> = {
  hirise: 1, ortho: 1, footprint: 1, route: 1,
  sites: 1, minerals: 1, labels: 1, geology: 1, traverse: 1,
}

interface LayerState {
  showHiRISE: boolean
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
  /** Per-layer opacity, fixed at 1.0. Kept so the globe's styling code reads one source. */
  opacity: Readonly<Record<LayerId, number>>
  view: MapView
  toggleHiRISE: () => void
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
  setView: (v: MapView) => void
}

export const useLayerStore = create<LayerState>(set => ({
  showHiRISE: true,
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
}))
