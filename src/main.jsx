import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import SensAItionSimulator from './SensAItion_Simulator'
import SensAItionCockpit from './SensAItion_Cockpit'

// View switch: #cockpit → fleet mission-control demo, otherwise single-site simulator.
function App() {
  const [view, setView] = useState(window.location.hash === '#cockpit' ? 'cockpit' : 'simulator')

  useEffect(() => {
    const onHash = () => setView(window.location.hash === '#cockpit' ? 'cockpit' : 'simulator')
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (v) => { window.location.hash = v === 'cockpit' ? '#cockpit' : '' }

  const tab = (active) => ({
    background: active ? '#1E8A4C' : '#FFFFFF',
    color: active ? '#fff' : '#4A6B57',
    border: '1px solid #D4E2DA',
    borderRadius: 6,
    padding: '5px 12px',
    fontWeight: 700,
    fontSize: 12,
    cursor: 'pointer',
  })

  return (
    <>
      <div style={{
        position: 'fixed', top: 8, right: 8, zIndex: 1000,
        display: 'flex', gap: 6, background: '#F4F7F5cc',
        padding: 4, borderRadius: 8, backdropFilter: 'blur(4px)',
      }}>
        <button style={tab(view === 'simulator')} onClick={() => go('simulator')}>Simulator</button>
        <button style={tab(view === 'cockpit')} onClick={() => go('cockpit')}>Cockpit</button>
      </div>
      {view === 'cockpit' ? <SensAItionCockpit /> : <SensAItionSimulator />}
    </>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
