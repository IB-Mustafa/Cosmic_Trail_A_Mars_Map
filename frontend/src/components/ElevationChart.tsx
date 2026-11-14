import { useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { downloadRouteExport, type RouteExportFormat } from '../api/cosmic'
import { useRouteStore } from '../store/routeStore'

// Blue = fine, pink = caution, orange = over limit. Validated for colour-blind
// separation on the dark card; every band is also named in the legend and tooltip.
const BAND_COLORS = { ok: '#4a9eff', caution: '#ff4d8d', over: '#ff9f43' } as const
const BAND_LABELS = { ok: 'ok', caution: 'caution', over: 'over limit' } as const
type Band = keyof typeof BAND_COLORS

const AXIS = '#8899bb'
const GRID = 'rgba(74,158,255,0.12)'

interface Point { km: number; elev: number; slope: number; band: Band }

export default function ElevationChart() {
  const { response, activeMode } = useRouteStore()
  const route = response?.routes[activeMode]
  // Thresholds come from the backend (params_used) so chart and router always agree.
  const caution = response?.params_used.caution_slope_deg ?? 10
  const max = response?.params_used.max_slope_deg ?? 15
  const [busy, setBusy] = useState<RouteExportFormat | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const download = async (fmt: RouteExportFormat) => {
    if (!response) return
    setBusy(fmt)
    setExportError(null)
    try {
      await downloadRouteExport(fmt, response, activeMode)
    } catch (e) {
      setExportError(`Export failed: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  const data = useMemo<Point[]>(() => {
    if (!route) return []
    const band = (s: number): Band => (s > max ? 'over' : s >= caution ? 'caution' : 'ok')
    let dist = 0
    return route.elevation_profile.map((elev, i) => {
      if (i > 0) {
        const [x0, y0] = route.xy[i - 1]
        const [x1, y1] = route.xy[i]
        dist += Math.hypot(x1 - x0, y1 - y0)
      }
      const slope = route.slope_profile[i] ?? 0
      return { km: dist / 1000, elev, slope, band: band(slope) }
    })
  }, [route, caution, max])

  // Runs of consecutive points in the same band → gradient stops + shaded warning zones.
  const { stops, zones } = useMemo(() => {
    const stops: { offset: number; color: string }[] = []
    const zones: { x1: number; x2: number; band: Band }[] = []
    if (data.length < 2) return { stops, zones }
    const total = data[data.length - 1].km || 1
    let runStart = 0
    for (let i = 1; i <= data.length; i++) {
      if (i < data.length && data[i].band === data[runStart].band) continue
      const b = data[runStart].band
      // Half a cell either side so a single steep cell is still visible.
      const x1 = data[Math.max(runStart - 1, 0)].km
      const x2 = data[Math.min(i, data.length - 1)].km
      stops.push({ offset: data[runStart].km / total, color: BAND_COLORS[b] })
      stops.push({ offset: data[i - 1].km / total, color: BAND_COLORS[b] })
      if (b !== 'ok') zones.push({ x1, x2, band: b })
      runStart = i
    }
    return { stops, zones }
  }, [data])

  if (!route) {
    return <div className="chart-empty"><span>Find a route to see its elevation profile</span></div>
  }

  return (
    <div className="chart">
      <div className="chart-head">
        <strong>Elevation profile · {activeMode === 'terrain' ? 'terrain-safe' : 'shortest'} route</strong>
        <span className="legend">
          <span><i style={{ background: BAND_COLORS.ok }} />slope &lt; {caution}°</span>
          <span><i style={{ background: BAND_COLORS.caution }} />{caution}–{max}° caution</span>
          <span><i style={{ background: BAND_COLORS.over }} />&gt; {max}° over limit</span>
        </span>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 12, bottom: 2, left: 4 }}>
            <defs>
              <linearGradient id="slopeGrad" x1="0" y1="0" x2="1" y2="0">
                {stops.map((s, i) => <stop key={i} offset={s.offset} stopColor={s.color} />)}
              </linearGradient>
            </defs>
            <CartesianGrid stroke={GRID} vertical={false} />
            {zones.map((z, i) => (
              <ReferenceArea key={i} x1={z.x1} x2={z.x2} ifOverflow="extendDomain"
                             fill={BAND_COLORS[z.band]} fillOpacity={0.14} stroke="none" />
            ))}
            <XAxis dataKey="km" type="number" domain={['dataMin', 'dataMax']}
                   tickFormatter={v => v.toFixed(1)} stroke={AXIS} tick={{ fill: AXIS, fontSize: 11 }}
                   tickLine={false} axisLine={{ stroke: GRID }}
                   label={{ value: 'distance (km)', position: 'insideBottomRight', offset: -2, fill: AXIS, fontSize: 11 }} />
            <YAxis dataKey="elev" domain={['auto', 'auto']} stroke={AXIS} width={58}
                   tick={{ fill: AXIS, fontSize: 11 }} tickLine={false} axisLine={false}
                   tickFormatter={v => Math.round(v).toString()}
                   label={{ value: 'elevation (m)', angle: -90, position: 'insideLeft', fill: AXIS, fontSize: 11 }} />
            <Tooltip
              cursor={{ stroke: 'rgba(232,240,255,0.35)', strokeWidth: 1 }}
              contentStyle={{
                background: 'rgba(13,25,54,0.95)', border: '1px solid rgba(74,158,255,0.3)',
                borderRadius: 10, color: '#e8f0ff', boxShadow: '0 0 20px rgba(74,158,255,0.25)',
              }}
              labelStyle={{ color: '#8899bb' }}
              itemStyle={{ color: '#e8f0ff' }}
              labelFormatter={v => `${Number(v).toFixed(2)} km`}
              formatter={(_v, _n, item) => {
                const p = item.payload as Point
                return [`${p.elev.toFixed(1)} m · slope ${p.slope.toFixed(1)}° (${BAND_LABELS[p.band]})`, 'elevation']
              }}
            />
            <Line type="monotone" dataKey="elev" stroke="url(#slopeGrad)" strokeWidth={2}
                  dot={false} activeDot={{ r: 5, fill: '#e8f0ff', stroke: '#4a9eff', strokeWidth: 2 }}
                  isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-actions">
        <button type="button" className="secondary" onClick={() => download('geojson')} disabled={busy !== null}
                title="Both routes as GeoJSON LineStrings of [lon, lat, elevation m] (selected route first), plus A and B">
          {busy === 'geojson' ? 'Preparing…' : '⬇ Download GeoJSON'}
        </button>
        <button type="button" className="secondary" onClick={() => download('briefing')} disabled={busy !== null}
                title="Plain-text briefing: length, climb, slope, warnings, science/thermal context, data sources">
          {busy === 'briefing' ? 'Preparing…' : '⬇ Download Briefing'}
        </button>
        {exportError && <span className="chart-error" role="alert">{exportError}</span>}
      </div>
    </div>
  )
}
