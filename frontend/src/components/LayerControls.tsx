import { useLayerStore, type HiriseStyle, type LayerId } from '../store/layerStore'
import { useRouteStore } from '../store/routeStore'
import { GAZETTEER } from '../mars'
import { USGS_GEOLOGY_URL } from '../api/cosmic'
import { geoUnitColor } from './Globe'

function Pill({ on, onClick, children, disabled, title }: {
  on: boolean; onClick: () => void; children: React.ReactNode; disabled?: boolean; title?: string
}) {
  const active = on && !disabled
  return (
    <button type="button" className={`pill ${active ? 'on' : ''}`} aria-pressed={active}
            onClick={onClick} disabled={disabled} title={title}>
      {children}
    </button>
  )
}

/** A layer toggle with its opacity slider (0–100 %) underneath. */
function LayerItem({ id, label, on, onClick, children, disabled, title }: {
  id: LayerId; label: string; on: boolean; onClick: () => void
  children: React.ReactNode; disabled?: boolean; title?: string
}) {
  const opacity = useLayerStore(s => s.opacity[id])
  const setOpacity = useLayerStore(s => s.setOpacity)
  const pct = Math.round(opacity * 100)
  return (
    <div className={`layer-item ${on && !disabled ? 'on' : ''}`}>
      <Pill on={on} onClick={onClick} disabled={disabled} title={title}>{children}</Pill>
      <label className="opacity" title={`${label} opacity`}>
        <input type="range" min={0} max={100} step={5} value={pct} disabled={disabled}
               aria-label={`${label} opacity`} aria-valuetext={`${pct}%`}
               onChange={e => setOpacity(id, +e.target.value / 100)} />
        <output>{pct}%</output>
      </label>
    </div>
  )
}

export default function LayerControls() {
  const l = useLayerStore()
  const georef = useRouteStore(s => s.georef)
  const terrain = useRouteStore(s => s.terrain)
  const ortho = useRouteStore(s => s.ortho)
  const hasOrtho = !!ortho?.available
  const minerals = useRouteStore(s => s.minerals)
  const hasMinerals = !!minerals?.available
  const geology = useRouteStore(s => s.geology)
  const curiosity = useRouteStore(s => s.curiosityRoute)?.features[0]
  const hasGeology = !!geology?.features.length
  const hasCuriosity = !!curiosity
  // How many detection sites fall inside the routing grid (honest context for the legend).
  const inArea = georef && minerals?.points
    ? minerals.points.filter(p => p.lon >= georef.west && p.lon <= georef.east && p.lat >= georef.south && p.lat <= georef.north).length
    : null
  const has3d = !!terrain?.available

  return (
    <section className="glass panel" data-occludes>
      <h2>Layers</h2>
      <div className="pills layer-grid">
        <LayerItem id="hirise" label="HiRISE terrain" on={l.showHiRISE} onClick={l.toggleHiRISE}>HiRISE terrain</LayerItem>
        <LayerItem id="ortho" label="HiRISE photo" on={l.showOrtho} onClick={l.toggleOrtho} disabled={!hasOrtho}
              title={hasOrtho
                ? `${ortho!.sources?.length ?? 0} HiRISE orthoimages merged and clipped to the study area `
                  + `(${ortho!.resolution_m} m/px, ${ortho!.credit}). Replaces the HiRISE terrain shading while on.`
                  + (ortho!.sources?.length ? '\n' + ortho!.sources.join('\n') : '')
                : ortho?.note ?? 'HiRISE photo mosaic not available from the backend'}>
          📷 HiRISE photo
        </LayerItem>
        <LayerItem id="footprint" label="Routable area" on={l.showFootprint} onClick={l.toggleFootprint} disabled={!georef}
              title="Dashed outline of the area the router covers (always shown while picking A/B)">
          Routable area
        </LayerItem>
        <LayerItem id="route" label="Route" on={l.showRoute} onClick={l.toggleRoute}>Route</LayerItem>
        <LayerItem id="sites" label="Science sites" on={l.showSites} onClick={l.toggleSites}>Science sites</LayerItem>
        <LayerItem id="minerals" label="Minerals" on={l.showMinerals} onClick={l.toggleMinerals} disabled={!hasMinerals}
              title={hasMinerals ? 'Aqueous-mineral detection sites (Ehlmann & Edwards 2014; CRISM, OMEGA, THEMIS)'
                                 : minerals?.note ?? 'Mineral data not available from the backend'}>
          🔬 Minerals (CRISM/OMEGA)
        </LayerItem>
        <LayerItem id="labels" label="Place names" on={l.showLabels} onClick={l.toggleLabels}
              title={`${GAZETTEER.count} official IAU/USGS names, bundled locally`}>
          Place names
        </LayerItem>
        <LayerItem id="geology" label="Geologic units" on={l.showGeology} onClick={l.toggleGeology} disabled={!hasGeology}
              title={hasGeology ? 'USGS geologic map units (Tanaka et al. 2014, SIM 3292) — click a unit for details'
                                : 'Geologic units not available from the backend'}>
          🪨 Geologic Units
        </LayerItem>
        <LayerItem id="traverse" label="Curiosity route" on={l.showTraverse} onClick={l.toggleTraverse} disabled={!hasCuriosity}
              title={hasCuriosity ? "NASA's proposed Curiosity path up Mount Sharp — click a waypoint for details"
                                  : 'Curiosity route not available from the backend'}>
          🛸 Curiosity route
        </LayerItem>
      </div>
      {(l.showGeology && hasGeology) || (l.showTraverse && hasCuriosity) ? (
        <div className="mineral-legend" role="group" aria-label="Reference layers legend">
          <ul>
            {l.showTraverse && hasCuriosity && (
              <li><i className="swatch line" /><span>🛸 Curiosity Official Route (NASA JPL)</span></li>
            )}
            {l.showGeology && geology!.features.map(f => (
              <li key={f.properties.unit}>
                <i className="swatch square" style={{ background: geoUnitColor(f.properties) }} />
                <span>{f.properties.unit} — {f.properties.name}</span>
                <small>{f.properties.age}</small>
              </li>
            ))}
          </ul>
          {l.showTraverse && hasCuriosity && (
            <p className="src">Route: <a href={curiosity!.properties.url} target="_blank" rel="noreferrer">NASA JPL — Curiosity's Proposed Path up Mount Sharp</a> (waypoints approximate).</p>
          )}
          {l.showGeology && hasGeology && (
            <p className="src">Source: <a href={USGS_GEOLOGY_URL} target="_blank" rel="noreferrer">USGS Geologic Map</a> — Tanaka et al. 2014, SIM 3292. Simplified, approximate unit areas.</p>
          )}
        </div>
      ) : null}
      {l.showMinerals && hasMinerals && (
        <div className="mineral-legend" role="group" aria-label="Minerals legend">
          <ul>
            {minerals!.legend!.map(it => (
              <li key={it.class}>
                <i className="swatch" style={{ background: it.color }} />
                <span>{it.label}</span>
                <small>{it.count.toLocaleString()} sites</small>
              </li>
            ))}
          </ul>
          <p>
            Detection <b>sites</b>, not a mineral map — one point per published detection (±~0.01°).
            {inArea !== null && <> {inArea === 0 ? 'None fall' : `${inArea} fall`} inside the routing area.</>}
          </p>
          <p className="src">Source: NASA MRO CRISM, Mars Express OMEGA, Mars Odyssey THEMIS — compiled by Ehlmann &amp; Edwards (2014), via NASA Mars Trek.</p>
        </div>
      )}
      <label className="style-select">
        HiRISE style
        <select value={l.hiriseStyle} disabled={!l.showHiRISE}
                onChange={e => l.setHiriseStyle(e.target.value as HiriseStyle)}>
          <option value="hillshade">Hillshade</option>
          <option value="elevation">Elevation</option>
          <option value="slope">Slope</option>
        </select>
      </label>
      <label className="slider" title={has3d
        ? 'Stretch heights relative to the Gale floor so slopes and craters stand out. Routing always uses true heights.'
        : terrain?.note ?? '3D terrain not available from the backend'}>
        <span>3D Exaggeration <b>{has3d ? `${l.exaggeration.toFixed(1)}×` : 'flat'}</b></span>
        <input type="range" min={1} max={5} step={0.5} value={l.exaggeration} disabled={!has3d}
               onChange={e => l.setExaggeration(parseFloat(e.target.value))} />
      </label>
      {georef && (
        <details className="georef">
          <summary>Overlay georeference</summary>
          <p>From the terrain file metadata: {georef.crsLabel}; {georef.width}×{georef.height} cells of {georef.cellM} m, pixel-edge bounds
            {' '}{georef.west.toFixed(4)}–{georef.east.toFixed(4)}°E, {Math.abs(georef.north).toFixed(4)}–{Math.abs(georef.south).toFixed(4)}°S.
            All layers: planetocentric latitude, east-positive longitude, Mars sphere R = 3 396 190 m.</p>
        </details>
      )}
    </section>
  )
}
