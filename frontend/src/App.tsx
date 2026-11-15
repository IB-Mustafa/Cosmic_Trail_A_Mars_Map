import { useEffect, useState } from 'react'
import { georefFromMetadata, getCuriosityRoute, getDatasets, getGeologicUnits, getHealth, getMetadata, getScienceCards, getMinerals, getOrthoInfo, getTerrainInfo, type ScienceCard } from './api/cosmic'
import { useRouteStore } from './store/routeStore'
import { useLayerStore } from './store/layerStore'
import Globe from './components/Globe'
import RoutePanel from './components/RoutePanel'
import LayerControls from './components/LayerControls'
import ElevationChart from './components/ElevationChart'
import Chatbot from './components/Chatbot'

export default function App() {
  const { dataset, setDataset, setGeoref, setTerrain, setOrtho, setMinerals, setGeology, setCuriosityRoute } = useRouteStore()
  const view = useLayerStore(s => s.view)
  const [sites, setSites] = useState<ScienceCard[]>([])
  const [backendError, setBackendError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then(() => getDatasets())
      .then(list => {
        // Prefer the real HiRISE dataset; fall back to whatever has terrain.
        const ds = list.find(d => d.id === 'hirise_gale' && d.terrain_available)
          ?? list.find(d => d.terrain_available && d.crs)
        if (ds) setDataset(ds); else setBackendError('No dataset with terrain is loaded in the backend.')
      })
      .catch(e => setBackendError(`Backend not reachable at localhost:8000 (${(e as Error).message}). Start it with: uvicorn app.main:app`))
    getScienceCards().then(setSites).catch(() => setSites([]))
    getMinerals().then(setMinerals).catch(() => setMinerals(null))
    getGeologicUnits().then(setGeology).catch(() => setGeology(null))
    getCuriosityRoute().then(setCuriosityRoute).catch(() => setCuriosityRoute(null))
  }, [setDataset, setMinerals, setGeology, setCuriosityRoute])

  // Georeference the overlays from the terrain file's own metadata (CRS + grid bounds).
  useEffect(() => {
    if (!dataset) return
    getMetadata(dataset.id)
      .then(m => setGeoref(georefFromMetadata(m)))
      .catch(() => setGeoref(null))
    // 3D height tiles (flat globe if the backend has none).
    getTerrainInfo(dataset.id).then(setTerrain).catch(() => setTerrain(null))
    // Optional HiRISE orthoimage tiles (toggle in Layers).
    getOrthoInfo(dataset.id).then(setOrtho).catch(() => setOrtho(null))
  }, [dataset, setGeoref, setTerrain, setOrtho])

  return (
    <div className={`app view-${view}`}>
      {/* Full-bleed map behind floating glass panels. Views are centred in the area the
          panels leave uncovered (src/mapFrame.ts). */}
      <div className="globe"><Globe sites={sites} /></div>
      <aside className="sidebar">
        <header className="glass brand" data-occludes>
          <h1>COSMIC TRAIL</h1>
          <p>Gale Crater · Mars route planner</p>
          {dataset && <span className="ds">{dataset.dataset_id.split('+')[0]}{dataset.is_synthetic ? ' (synthetic)' : ''}</span>}
        </header>
        {backendError && <p className="error">{backendError}</p>}
        {dataset?.synthetic_warning && <p className="error">{dataset.synthetic_warning}</p>}
        {/* Route planning belongs to the study area; hidden in the Whole Mars view. */}
        {view === 'study' && <RoutePanel />}
        <LayerControls />
      </aside>
      {/* Bottom dock: hover-info bar + elevation panel (study view only). */}
      <div className="dock">
        <div id="inspector-slot" className="inspector-slot" />
        {view === 'study' && <section className="glass bottom" data-occludes><ElevationChart /></section>}
      </div>
      <Chatbot />
    </div>
  )
}
