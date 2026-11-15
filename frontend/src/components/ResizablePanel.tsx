import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'

// A bottom-docked glass panel the user can resize: drag the top edge (height), the right edge
// (width) or the top-right corner (both). The panel stays anchored bottom-left. Handles are
// keyboard-operable (arrow keys, Shift = bigger steps); double-click a handle to reset.
// The chosen size is remembered in this browser. The map re-frames itself automatically:
// Globe.tsx observes the dock's size (src/mapFrame.ts).

const STORAGE_KEY = 'cosmic-trail.elevation-panel-size'
export const DEFAULT_HEIGHT = 240
const MIN_HEIGHT = 170
const MIN_WIDTH = 380
const STEP = 16
const BIG_STEP = 64

type Size = { h: number; w: number | null }   // w = null → full dock width
type Edge = 'top' | 'right' | 'corner'

function loadSize(): Size {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const s = JSON.parse(raw) as Partial<Size>
      if (typeof s.h === 'number' && Number.isFinite(s.h)) {
        return { h: s.h, w: typeof s.w === 'number' && Number.isFinite(s.w) ? s.w : null }
      }
    }
  } catch { /* storage unavailable (private window, blocked) → defaults */ }
  return { h: DEFAULT_HEIGHT, w: null }
}

function saveSize(s: Size) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)) } catch { /* not persisted; fine */ }
}

/** Largest size that keeps the panel inside the window (room left for the top toolbar). */
function limits(panel: HTMLElement | null) {
  const dock = panel?.parentElement
  const maxW = Math.max(MIN_WIDTH, dock?.getBoundingClientRect().width ?? window.innerWidth)
  const maxH = Math.max(MIN_HEIGHT, window.innerHeight - 170)
  return { maxW, maxH }
}

export default function ResizablePanel({ children, className = '' }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLElement>(null)
  const [size, setSize] = useState<Size>(loadSize)
  const [dragging, setDragging] = useState<Edge | null>(null)
  const drag = useRef<{ x: number; y: number; h: number; w: number; edge: Edge } | null>(null)

  const clamp = useCallback((s: Size): Size => {
    const { maxW, maxH } = limits(ref.current)
    const h = Math.round(Math.min(maxH, Math.max(MIN_HEIGHT, s.h)))
    // Dragging back to (nearly) the full width returns to "full width", which follows the window.
    const w = s.w === null || s.w >= maxW - 4 ? null : Math.round(Math.min(maxW, Math.max(MIN_WIDTH, s.w)))
    return { h, w }
  }, [])

  // Keep the stored size valid when the window shrinks.
  useEffect(() => {
    const onResize = () => setSize(s => clamp(s))
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [clamp])

  useEffect(() => { if (!dragging) saveSize(size) }, [size, dragging])

  const currentWidth = () => ref.current?.getBoundingClientRect().width ?? MIN_WIDTH

  const onPointerDown = (edge: Edge) => (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, y: e.clientY, h: size.h, w: currentWidth(), edge }
    setDragging(edge)
  }

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    const dy = d.y - e.clientY          // dragging the top edge up makes the panel taller
    const dx = e.clientX - d.x          // dragging the right edge right makes it wider
    setSize(s => clamp({
      h: d.edge === 'right' ? s.h : d.h + dy,
      w: d.edge === 'top' ? s.w : d.w + dx,
    }))
  }

  const endDrag = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    drag.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    setDragging(null)
  }

  const reset = (edge: Edge) => () => setSize(s => clamp({
    h: edge === 'right' ? s.h : DEFAULT_HEIGHT,
    w: edge === 'top' ? s.w : null,
  }))

  const onKeyDown = (edge: Edge) => (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? BIG_STEP : STEP
    let dh = 0, dw = 0
    if (edge !== 'right' && e.key === 'ArrowUp') dh = step
    else if (edge !== 'right' && e.key === 'ArrowDown') dh = -step
    else if (edge !== 'top' && e.key === 'ArrowRight') dw = step
    else if (edge !== 'top' && e.key === 'ArrowLeft') dw = -step
    else if (e.key === 'Home' || e.key === 'Enter') { reset(edge)(); e.preventDefault(); return }
    else return
    e.preventDefault()
    setSize(s => clamp({ h: s.h + dh, w: dw ? (s.w ?? currentWidth()) + dw : s.w }))
  }

  const handle = (edge: Edge, label: string) => ({
    className: `resize-handle resize-${edge}`,
    role: 'separator',
    tabIndex: 0,
    'aria-label': label,
    'aria-orientation': (edge === 'right' ? 'vertical' : 'horizontal') as 'vertical' | 'horizontal',
    ...(edge !== 'right' ? { 'aria-valuenow': size.h, 'aria-valuemin': MIN_HEIGHT } : {}),
    title: `${label} — drag, or use the arrow keys (Shift for bigger steps). Double-click to reset.`,
    onPointerDown: onPointerDown(edge),
    onPointerMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    onDoubleClick: reset(edge),
    onKeyDown: onKeyDown(edge),
  })

  const style = {
    '--panel-h': `${size.h}px`,
    ...(size.w !== null ? { '--panel-w': `${size.w}px` } : {}),
  } as CSSProperties

  return (
    <section ref={ref} className={`glass bottom resizable${dragging ? ' is-resizing' : ''} ${className}`}
             style={style} data-occludes>
      {children}
      <div {...handle('top', 'Resize panel height')}><span className="grip" /></div>
      <div {...handle('right', 'Resize panel width')}><span className="grip" /></div>
      <div {...handle('corner', 'Resize panel height and width')} />
      {dragging && (
        <span className="resize-readout" aria-live="polite">
          {Math.round(size.w ?? currentWidth())} × {size.h}px
        </span>
      )}
    </section>
  )
}
