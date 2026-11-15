// ARIA — Astronaut Route Intelligence Assistant.
// Rule-based and offline (app/assistant.py + aria_nlu.py + aria_templates.py): answers come from
// the terrain grid, the last route, bundled mineral sites, cited science cards and published
// facts — no language model. The last few messages are sent with each question so ARIA can
// follow up ("and at night?", "what about south?"); nothing is stored on the server.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react'
import { askAssistant, routeSummary, type AssistantAction, type AssistantReply, type ChatTurn } from '../api/cosmic'
import { useRouteStore } from '../store/routeStore'
import { centerMapOn, getMapCenter } from './Globe'

/** `local`: a note from the app itself (greeting, "B set…", errors), not sent back as conversation. */
interface Msg { role: 'aria' | 'user'; text: string; reply?: AssistantReply; local?: boolean }

const HISTORY_TURNS = 6   // earlier messages sent with each question

/** Reply text → paragraphs, with the final "Source: …" line split off. */
function splitReply(text: string): { paras: string[]; source: string | null } {
  const paras = text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)
  const last = paras[paras.length - 1]
  if (last?.startsWith('Source:')) return { paras: paras.slice(0, -1), source: last.slice('Source:'.length).trim() }
  return { paras, source: null }
}

const GREETING =
  "Hello! I'm ARIA — your Astronaut Route Intelligence Assistant. I'm analysing terrain data for Gale Crater. " +
  'Ask me about slopes, hazards, elevation, minerals, your route or Mars geology. I answer from the NASA/USGS data ' +
  'loaded in COSMIC TRAIL and say where each answer comes from. I am rule-based (no AI model) and work offline.'

const QUICK = ['Am I safe here?', 'What minerals are nearby?', 'Analyze my route', 'How cold is it?']

/** Data-source badges shown under each reply (none when the reply used no data, e.g. the fallback). */
function badges(source: string): string[] {
  const s = source.toLowerCase(), out: string[] = []
  if (!s.trim()) return out
  if (s.includes('hirise')) out.push('📡 HiRISE Data')
  if (s.includes('usgs')) out.push('🗺 USGS Gale DEM')
  if (s.includes('mola')) out.push('🛰 MOLA')
  if (s.includes('crism')) out.push('🔬 CRISM/OMEGA Data')
  if (s.includes('route')) out.push('🧭 Route result')
  if (s.includes('curiosity') || s.includes('science card') || s.includes('published') || s.includes('pia16913')
      || s.includes('hassler')) out.push('📚 Published studies')
  if (s.includes('general mars knowledge') || s.includes('mars fact sheet') || s.includes('opportunity mission'))
    out.push('🌍 General Mars facts')
  return out
}

/** ARIA's offer to centre the map on a place the user named. */
interface MoveMapAction { type: 'move_map'; lon: number; lat: number; label: string }

// Panel size: dragged from the top-left corner (the panel is anchored bottom-right).
const SIZE_KEY = 'cosmic-trail:aria-size'
const MIN = { w: 300, h: 200 }
const MAX = { w: 600, h: 500 }
const DEFAULT_SIZE = { w: 380, h: 420 }
const PANEL_BOTTOM = 344   // CSS .aria-panel bottom offset; the panel must also fit above it
type Size = { w: number; h: number }

const clampSize = (sz: Size): Size => ({
  w: Math.round(Math.min(MAX.w, Math.max(MIN.w, sz.w))),
  h: Math.round(Math.min(MAX.h, Math.max(MIN.h, sz.h))),
})

function loadSize(): Size {
  try {
    const v = JSON.parse(localStorage.getItem(SIZE_KEY) ?? 'null')
    if (v && Number.isFinite(v.w) && Number.isFinite(v.h)) return clampSize(v)
  } catch { /* storage unavailable: use the default */ }
  return DEFAULT_SIZE
}

function saveSize(sz: Size) {
  try { localStorage.setItem(SIZE_KEY, JSON.stringify(sz)) } catch { /* ignore */ }
}

/** Never let the panel run off the top or left of a small window. */
function useViewportLimit() {
  const get = () => ({ w: window.innerWidth - 32, h: window.innerHeight - PANEL_BOTTOM - 16 })
  const [lim, setLim] = useState(get)
  useEffect(() => {
    const on = () => setLim(get())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return lim
}

const fmt = (lon: number, lat: number) =>
  `${Math.abs(lat).toFixed(3)}°${lat < 0 ? 'S' : 'N'}, ${Math.abs(lon).toFixed(3)}°${lon < 0 ? 'W' : 'E'}`

export default function Chatbot() {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([{ role: 'aria', text: GREETING, local: true }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const { dataset, response, activeMode, setEnd, setPickMessage } = useRouteStore()
  const setDestination = (a: AssistantAction) => {
    setEnd({ lon: a.lon, lat: a.lat })
    setPickMessage({ target: 'end', kind: 'ok', text: `B set to ${a.label} (${fmt(a.lon, a.lat)}) by ARIA. Press Find Route.` })
    setMsgs(m => [...m, { role: 'aria', text: `📍 Destination B set to ${a.label}. Press Find Route to plan the path.`, local: true }])
  }
  const moveMap = (a: MoveMapAction) => {
    const ok = centerMapOn(a.lon, a.lat)
    setMsgs(m => [...m, { role: 'aria', local: true, text: ok
      ? `🗺 Moved the map to ${a.label} (${fmt(a.lon, a.lat)}). My answers now use this point.`
      : "The map isn't ready yet, so I couldn't move it. Please try again in a moment." }])
  }
  const [size, setSize] = useState<Size>(loadSize)
  const drag = useRef<{ x: number; y: number; w: number; h: number } | null>(null)
  const limit = useViewportLimit()

  // Auto-scroll to the latest message (also when the panel opens or is resized).
  // Jump (not smooth-scroll) to the newest message right after the DOM updates: a smooth scroll, or one
  // deferred to the next animation frame, can lag far behind while the 3D globe is busy rendering.
  useLayoutEffect(() => {
    const l = listRef.current
    if (l) l.scrollTop = l.scrollHeight
  }, [msgs, busy, open, size])
  useEffect(() => { if (open) inputRef.current?.focus() }, [open])

  const onResizeStart = (e: PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, y: e.clientY, w: size.w, h: size.h }
  }
  const onResizeMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    // Dragging up/left grows the panel (it is anchored at the bottom-right).
    setSize(clampSize({ w: d.w + (d.x - e.clientX), h: d.h + (d.y - e.clientY) }))
  }
  const onResizeEnd = useCallback(() => {
    if (!drag.current) return
    drag.current = null
    setSize(sz => { saveSize(sz); return sz })
  }, [])
  const onResizeKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 50 : 20
    const delta = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key]
    if (!delta) return
    e.preventDefault()
    setSize(sz => { const next = clampSize({ w: sz.w + delta[0], h: sz.h + delta[1] }); saveSize(next); return next })
  }
  const shown = { w: Math.min(size.w, Math.max(MIN.w, limit.w)), h: Math.min(size.h, Math.max(MIN.h, limit.h)) }

  const send = async (text: string) => {
    const q = text.trim()
    if (!q || busy) return
    const history: ChatTurn[] = msgs.filter(m => !m.local).slice(-HISTORY_TURNS)
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.text, topic: m.reply?.topic }))
    setMsgs(m => [...m, { role: 'user', text: q }])
    setInput('')
    setBusy(true)
    const center = getMapCenter()
    const route = response?.routes[activeMode]
    try {
      const reply = await askAssistant(q, {
        current_lon: center?.lon, current_lat: center?.lat, dataset_id: dataset?.id,
        last_route: route ? routeSummary(route, response?.params_used.caution_slope_deg) : null,
      }, history)
      setMsgs(m => [...m, { role: 'aria', text: reply.reply, reply }])
    } catch (e) {
      const msg = (e as Error).message
      const text = /Failed to fetch|NetworkError|Load failed/i.test(msg)
        ? "I can't reach the COSMIC TRAIL backend right now. Is it running (uvicorn app.main:app on port 8000)?"
        : `Something went wrong on the server (${msg}). Please try again.`
      setMsgs(m => [...m, { role: 'aria', text, local: true }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button className={`aria-fab ${open ? 'open' : ''}`} data-occludes onClick={() => setOpen(o => !o)}
              aria-expanded={open} aria-controls="aria-panel" title="ARIA — rule-based terrain assistant">
        🤖 ARIA
      </button>
      {open && (
        <section id="aria-panel" className="aria-panel glass" data-occludes aria-label="ARIA assistant"
                 style={{ '--aria-w': `${shown.w}px`, '--aria-h': `${shown.h}px` } as CSSProperties}>
          <div className="aria-resize" role="separator" aria-orientation="horizontal" tabIndex={0}
               aria-label="Resize ARIA panel (drag, or use arrow keys)" title="Drag to resize"
               aria-valuemin={MIN.h} aria-valuemax={MAX.h} aria-valuenow={size.h}
               onPointerDown={onResizeStart} onPointerMove={onResizeMove}
               onPointerUp={onResizeEnd} onPointerCancel={onResizeEnd} onKeyDown={onResizeKey}>⤡</div>
          <header>
            <div>
              <h3>ARIA</h3>
              <p>Astronaut Route Intelligence Assistant · rule-based · offline</p>
            </div>
            <button className="close" aria-label="Close ARIA" onClick={() => setOpen(false)}>×</button>
          </header>
          <div className="aria-msgs" ref={listRef} aria-live="polite">
            {msgs.map((m, i) => (
              <div key={i} className={`aria-msg ${m.role}`}>
                {(() => {
                  const { paras, source } = m.reply ? splitReply(m.text) : { paras: [m.text], source: null }
                  return <>
                    {paras.map((p, j) => <p key={j}>{p}</p>)}
                    {source && <p className="aria-source"><span>Source</span> {source}</p>}
                  </>
                })()}
                {m.reply?.suggestions && m.reply.suggestions.length > 0 && (
                  <div className="aria-suggest">
                    {m.reply.suggestions.map(s => (
                      <button key={s} type="button" onClick={() => send(s)} disabled={busy}>{s}</button>
                    ))}
                  </div>
                )}
                {(m.reply?.data as { action?: AssistantAction } | undefined)?.action?.type === 'set_destination' && (() => {
                  const a = (m.reply!.data as { action: AssistantAction }).action
                  return (
                    <button type="button" className="aria-action" onClick={() => setDestination(a)}>
                      📍 Set as Destination B — {a.label}
                    </button>
                  )
                })()}
                {(m.reply?.data as { move_map?: MoveMapAction } | undefined)?.move_map?.type === 'move_map' && (() => {
                  const a = (m.reply!.data as { move_map: MoveMapAction }).move_map
                  return (
                    <button type="button" className="aria-action" onClick={() => moveMap(a)}>
                      🗺 Move map to {a.label}
                    </button>
                  )
                })()}
                {m.reply && (
                  <div className="aria-meta">
                    {badges(m.reply.data_source).map(b => <span key={b} className="badge">{b}</span>)}
                    <span className={`conf ${m.reply.confidence}`}>confidence: {m.reply.confidence}</span>
                    <span className="where">📍 {fmt(m.reply.location.lon, m.reply.location.lat)}</span>
                  </div>
                )}
                {m.reply?.caveat && <p className="aria-caveat">{m.reply.caveat}</p>}
              </div>
            ))}
            {busy && <div className="aria-msg aria typing"><p>Analysing terrain…</p></div>}
          </div>
          <div className="aria-quick">
            {QUICK.map(q => <button key={q} onClick={() => send(q)} disabled={busy}>{q}</button>)}
          </div>
          <form className="aria-input" onSubmit={e => { e.preventDefault(); send(input) }}>
            <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} maxLength={500}
                   placeholder="Ask about slope, hazards, minerals…" aria-label="Message ARIA" />
            <button type="submit" className="primary" disabled={busy || !input.trim()}>Send</button>
          </form>
          <p className="aria-foot">Answers use the point at the centre of the map. Not a safety certification.</p>
        </section>
      )}
    </>
  )
}
