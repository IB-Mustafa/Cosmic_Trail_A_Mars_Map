import { create } from 'zustand'
import type { CuriosityRoute, Dataset, GeologicUnits, Georef, LonLat, MineralsLayer, OrthoInfo, RouteResponse, TerrainInfo } from '../api/cosmic'

// Bradbury Landing, Curiosity's landing site (4.5895°S, 137.4417°E — see app/science.py).
export const BRADBURY: LonLat = { lon: 137.4417, lat: -4.5895 }
// Default destination: ~1.9 km east of Bradbury, inside the HiRISE grid.
export const DEFAULT_END: LonLat = { lon: 137.47, lat: -4.58 }

export type ActiveMode = 'terrain' | 'shortest'
export type PickTarget = 'start' | 'end' | null

/** Feedback from the last globe pick (validated against the backend's routing coverage). */
export interface PickMessage { target: 'start' | 'end'; kind: 'checking' | 'ok' | 'warn' | 'error'; text: string }

interface RouteState {
  dataset: Dataset | null
  georef: Georef | null
  terrain: TerrainInfo | null
  ortho: OrthoInfo | null
  minerals: MineralsLayer | null
  geology: GeologicUnits | null
  curiosityRoute: CuriosityRoute | null
  start: LonLat
  end: LonLat
  response: RouteResponse | null
  activeMode: ActiveMode
  picking: PickTarget
  pickMessage: PickMessage | null
  setDataset: (d: Dataset) => void
  setGeoref: (g: Georef | null) => void
  setTerrain: (t: TerrainInfo | null) => void
  setOrtho: (o: OrthoInfo | null) => void
  setMinerals: (m: MineralsLayer | null) => void
  setGeology: (g: GeologicUnits | null) => void
  setCuriosityRoute: (r: CuriosityRoute | null) => void
  setStart: (p: LonLat) => void
  setEnd: (p: LonLat) => void
  setResponse: (r: RouteResponse | null) => void
  setActiveMode: (m: ActiveMode) => void
  setPicking: (p: PickTarget) => void
  setPickMessage: (m: PickMessage | null) => void
}

export const useRouteStore = create<RouteState>(set => ({
  dataset: null,
  georef: null,
  terrain: null,
  ortho: null,
  minerals: null,
  geology: null,
  curiosityRoute: null,
  start: BRADBURY,
  end: DEFAULT_END,
  response: null,
  activeMode: 'terrain',
  picking: null,
  pickMessage: null,
  setDataset: dataset => set({ dataset }),
  setGeoref: georef => set({ georef }),
  setTerrain: terrain => set({ terrain }),
  setOrtho: ortho => set({ ortho }),
  setMinerals: minerals => set({ minerals }),
  setGeology: geology => set({ geology }),
  setCuriosityRoute: curiosityRoute => set({ curiosityRoute }),
  setStart: start => set({ start }),
  setEnd: end => set({ end }),
  setResponse: response => set({ response }),
  setActiveMode: activeMode => set({ activeMode }),
  setPicking: picking => set({ picking, ...(picking ? { pickMessage: null } : {}) }),
  setPickMessage: pickMessage => set({ pickMessage }),
}))
