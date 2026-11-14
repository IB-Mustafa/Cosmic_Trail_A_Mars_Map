import { useState } from 'react'
import { cautionStretches, getRoute, type LonLat, type RouteResponse, type RouteResult } from '../api/cosmic'
import { BRADBURY, DEFAULT_END, useRouteStore, type ActiveMode, type PickMessage } from '../store/routeStore'

// Curiosity's top speed on flat, hard ground is 4 cm/s (NASA MSL rover specifications).
// Real drives are much slower (hazard checks, stops), so this is a lower bound.
const ROVER_TOP_SPEED_M_S = 0.04

function fmtDuration(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return h > 0 ? `${h} h ${m} min` : `${m} min`
}

/** Contiguous runs of route cells steeper than the caution slope. */
const cautionSegments = (r: RouteResult, caution: number) => cautionStretches(r, caution).segments

type Verdict = { text: string; kind: 'good' | 'bad' | 'neutral' }

/** Verdicts from the numbers, not hard-coded: RISKY only when the shortest path is steeper than caution. */
function verdicts(res: RouteResponse, s: RouteResult, t: RouteResult): { shortest: Verdict; terrain: Verdict } {
  const caution = res.params_used.caution_slope_deg
  const relation = res.comparison?.relation
  if (relation === 'identical' || relation === 'equivalent') {
    const same: Verdict = { text: '≈ Same route', kind: 'neutral' }
    return { shortest: same, terrain: same }
  }
  const terrainSafer = t.slope_max_deg < s.slope_max_deg || t.cells_above_caution < s.cells_above_caution
  if (!terrainSafer) {
    return { shortest: { text: '✅ PREFERRED', kind: 'good' }, terrain: { text: 'Longer, not safer', kind: 'neutral' } }
  }
  const risky = s.slope_max_deg > caution || s.cells_above_caution > 0
  return {
    shortest: risky ? { text: '⚠️ RISKY', kind: 'bad' } : { text: 'Steeper', kind: 'neutral' },
    terrain: { text: '✅ PREFERRED', kind: 'good' },
  }
}

function CompareTable({ res }: { res: RouteResponse }) {
  const s = res.routes.shortest, t = res.routes.terrain
  if (!s || !t) return null
  const caution = res.params_used.caution_slope_deg
  const v = verdicts(res, s, t)
  const rows: [string, (r: RouteResult) => string, string?][] = [
    ['Distance', r => `${(r.surface_length_3d_m / 1000).toFixed(2)} km`, '3D surface distance'],
    ['Max Slope', r => `${r.slope_max_deg.toFixed(1)}°`],
    ['Avg Slope', r => `${r.slope_mean_deg.toFixed(1)}°`],
    ['Elevation Gain', r => `+${r.elevation_gain_m.toFixed(0)} m`],
    ['Caution Segments', r => `${cautionSegments(r, caution)}`,
     `Stretches of the route steeper than the ${caution}° caution slope (NASA MSL moderate-slope threshold)`],
  ]
  return (
    <table className="compare">
      <thead>
        <tr><th scope="col">Metric</th><th scope="col" className="shortest">Shortest Path</th><th scope="col" className="terrain">Terrain-Safe</th></tr>
      </thead>
      <tbody>
        {rows.map(([label, f, title]) => (
          <tr key={label}><th scope="row" title={title}>{label}</th><td>{f(s)}</td><td>{f(t)}</td></tr>
        ))}
        <tr className="verdict">
          <th scope="row">Verdict</th>
          <td className={v.shortest.kind}>{v.shortest.text}</td>
          <td className={v.terrain.kind}>{v.terrain.text}</td>
        </tr>
      </tbody>
    </table>
  )
}

function PointInput({ label, value, onChange, onPick, picking, message }: {
  label: string; value: LonLat; onChange: (p: LonLat) => void; onPick: () => void; picking: boolean
  message?: PickMessage | null
}) {
  return (
    <fieldset>
      <legend>{label}</legend>
      <label>Lat <input type="number" step="0.0001" value={value.lat}
        onChange={e => onChange({ ...value, lat: parseFloat(e.target.value) })} /></label>
      <label>Lon <input type="number" step="0.0001" value={value.lon}
        onChange={e => onChange({ ...value, lon: parseFloat(e.target.value) })} /></label>
      <button type="button" className={picking ? 'active' : ''} onClick={onPick}
              title="Click a point inside the routable area on the globe">{picking ? 'Click globe…' : 'Pick'}</button>
      {message && <p className={`pick-msg ${message.kind}`} role="status">{message.text}</p>}
    </fieldset>
  )
}

export default function RoutePanel() {
  const {
    dataset, start, end, response, activeMode, picking, pickMessage,
    setStart, setEnd, setResponse, setActiveMode, setPicking, setPickMessage,
  } = useRouteStore()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const findRoute = async () => {
    if (!dataset) return
    setBusy(true); setError(null)
    try {
      setResponse(await getRoute(dataset.id, start, end))
    } catch (e) {
      setResponse(null)
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setStart(BRADBURY); setEnd(DEFAULT_END); setResponse(null); setError(null); setPicking(null); setPickMessage(null)
  }

  return (
    <section className="glass panel" data-occludes>
      <h2>Route planner</h2>
      <PointInput label="Start (A)" value={start} onChange={setStart}
                  picking={picking === 'start'} onPick={() => setPicking(picking === 'start' ? null : 'start')}
                  message={pickMessage?.target === 'start' ? pickMessage : null} />
      <PointInput label="Destination (B)" value={end} onChange={setEnd}
                  picking={picking === 'end'} onPick={() => setPicking(picking === 'end' ? null : 'end')}
                  message={pickMessage?.target === 'end' ? pickMessage : null} />
      <div className="row">
        <button className="primary" onClick={findRoute} disabled={busy || !dataset}>{busy ? 'Routing…' : 'Find Route'}</button>
        <button className="secondary" onClick={reset}>Reset</button>
      </div>
      {error && <p className="error">{error}</p>}

      {response && (
        <div className="results">
          {(['terrain', 'shortest'] as ActiveMode[]).map(m => {
            const r = response.routes[m]
            if (!r) return null
            const secs = r.surface_length_3d_m / ROVER_TOP_SPEED_M_S
            return (
              <button key={m} className={`route-card ${m} ${m === activeMode ? 'active' : ''}`}
                      onClick={() => setActiveMode(m)}>
                <strong>{m === 'terrain' ? 'Terrain-safe' : 'Shortest'} <i className={`route-key ${m}`} aria-hidden /></strong>
                <span className="km">{(r.surface_length_3d_m / 1000).toFixed(2)} km</span>
                <span>≥ {fmtDuration(secs)} at rover top speed</span>
                <span>+{r.elevation_gain_m.toFixed(0)} m / −{r.elevation_loss_m.toFixed(0)} m · max {r.slope_max_deg.toFixed(1)}°</span>
                {r.warnings.map((w, i) => <em key={i}>{w.text}</em>)}
              </button>
            )
          })}
          <CompareTable res={response} />
          {response.routes[activeMode]?.context && (() => {
            const c = response.routes[activeMode]!.context!
            return (
              <ul className="route-context" aria-label={`Context for the ${activeMode === 'terrain' ? 'terrain-safe' : 'shortest'} route`}>
                {c.science && <li>{c.science.text}</li>}
                <li className={c.thermal.crossings ? 'warn' : c.thermal.checked ? '' : 'muted'}>{c.thermal.text}</li>
                <li>{c.data.text}</li>
              </ul>
            )
          })()}
          {response.tradeoff_summary && <p className="note tradeoff">{response.tradeoff_summary}</p>}
          {response.synthetic_warning && <p className="error">{response.synthetic_warning}</p>}
          <p className="note">
            Time = 3D distance ÷ 4 cm/s (Curiosity top speed, NASA). A lower bound — real drives are slower.
            {' '}{response.params_used.params_note}
          </p>
        </div>
      )}
    </section>
  )
}
