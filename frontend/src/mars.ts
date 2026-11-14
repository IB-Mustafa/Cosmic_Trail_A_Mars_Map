// Mars body + coordinate convention shared by every globe layer.
//
// ONE convention everywhere: planetocentric latitude, east-positive longitude in
// −180…180°, on the IAU Mars sphere R = 3 396 190 m.
//   • HiRISE DTMs / analysis grid: eqc on R = 3 396 190 m, planetocentric, east-positive.
//   • USGS MSL Gale DEM (gap fill): eqc on the same sphere.
//   • NASA Mars Trek Viking MDIM 2.1 tiles: planetocentric, east-positive, tiles start at −180°.
//   • IAU/USGS gazetteer: planetocentric, 0–360° east → converted to −180…180 at build time
//     (scripts/build_mars_labels.py).
//   • Science-card / routing coordinates from the backend: planetocentric, east-positive.
// On a sphere, planetocentric = geodetic latitude, so Cesium needs no conversion.
import { Ellipsoid } from 'cesium'
import labels from './data/mars_labels.json'

export const MARS_RADIUS = 3396190
export const MARS = new Ellipsoid(MARS_RADIUS, MARS_RADIUS, MARS_RADIUS)
Ellipsoid.default = MARS

export interface MarsFeature {
  n: string   // official name
  t: string   // feature type (Crater, Vallis, Mons…)
  d: number   // diameter, km (0 = not given)
  lat: number
  lon: number
  id: number | null
}

export const GAZETTEER = labels as {
  source: string; source_url: string; feature_url: string; convention: string; built: string
  count: number; features: MarsFeature[]
}

export const featureUrl = (f: MarsFeature) =>
  f.id ? GAZETTEER.feature_url.replace('{id}', String(f.id)) : GAZETTEER.source_url

export const GALE = GAZETTEER.features.find(f => f.n === 'Gale' && f.t === 'Crater')!

/** Normalise any longitude to −180…180 (east-positive). */
export const wrapLon = (lon: number) => ((((lon + 180) % 360) + 360) % 360) - 180
