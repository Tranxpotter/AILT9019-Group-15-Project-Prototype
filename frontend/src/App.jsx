import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import Header from './components/Header'
import FilterChips from './components/FilterChips'
import ChatBox from './components/ChatBox'
import MapView from './components/MapView'
import RestaurantList from './components/RestaurantList'
import RestaurantDetail from './components/RestaurantDetail'
import MemoryPanel from './components/MemoryPanel'
import LLMConfigModal from './components/LLMConfigModal'

const EMPTY_FILTERS = {
  meal: '',
  priceLevel: null,
  cuisines: [],
  dietary: [],
  openAt: '',
  excludePrevious: false,
}

export default function App() {
  const [meta, setMeta] = useState(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [items, setItems] = useState([])
  const [mode, setMode] = useState('explore') // 'explore' | 'chat'
  const [chatModeLabel, setChatModeLabel] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [thread, setThread] = useState([])
  const [busy, setBusy] = useState(false)
  const [llmConfig, setLlmConfig] = useState(null)
  const [showConfig, setShowConfig] = useState(false)
  const [showMemory, setShowMemory] = useState(false)
  const [memory, setMemory] = useState({ suggestions: [], reviews: [] })
  const [error, setError] = useState('')

  const refreshMeta = useCallback(async () => {
    try {
      const m = await api.meta()
      setMeta(m)
    } catch (e) {
      setError(`Cannot reach backend: ${e.message}`)
    }
  }, [])

  const refreshLLM = useCallback(async () => {
    try {
      setLlmConfig(await api.getLLMConfig())
    } catch {
      /* non-fatal */
    }
  }, [])

  const refreshMemory = useCallback(async () => {
    try {
      setMemory(await api.memory())
    } catch {
      /* non-fatal */
    }
  }, [])

  useEffect(() => {
    refreshMeta()
    refreshLLM()
    refreshMemory()
  }, [refreshMeta, refreshLLM, refreshMemory])

  const explore = useCallback(
    async (f) => {
      setMode('explore')
      setBusy(true)
      try {
        const res = await api.listRestaurants({
          meal: f.meal || undefined,
          cuisine: f.cuisines.length ? f.cuisines : undefined,
          price_level: f.priceLevel || undefined,
          dietary: f.dietary.length ? f.dietary : undefined,
          open_at: f.openAt || undefined,
          exclude_previous: f.excludePrevious,
          limit: 20,
        })
        setItems(res.items)
      } catch (e) {
        setError(`Explore failed: ${e.message}`)
      } finally {
        setBusy(false)
      }
    },
    [],
  )

  useEffect(() => {
    if (meta) explore(filters)
  }, [meta, filters, explore])

  const sendChat = useCallback(
    async (message) => {
      if (!message.trim()) return
      setThread((t) => [...t, { role: 'user', text: message }])
      setBusy(true)
      setError('')
      try {
        const res = await api.chat({
          message,
          filters: {
            meal: filters.meal || null,
            cuisines: filters.cuisines,
            price_level: filters.priceLevel,
            open_at: filters.openAt || null,
            dietary: filters.dietary,
          },
          exclude_previous: filters.excludePrevious,
          limit: 5,
        })
        setThread((t) => [
          ...t,
          {
            role: 'assistant',
            summary: res.summary,
            picks: res.picks,
            mode: res.mode,
            structured: res.structured,
            provider_label: res.provider_label,
          },
        ])
        setMode('chat')
        setChatModeLabel(
          res.mode === 'llm' ? `LLM: ${res.provider_label}` : 'Demo mode (keyword parser)',
        )
        setItems(res.picks)
      } catch (e) {
        setError(`Chat failed: ${e.message}`)
        setThread((t) => [...t, { role: 'assistant', summary: `⚠️ ${e.message}`, picks: [] }])
      } finally {
        setBusy(false)
      }
    },
    [filters],
  )

  const onReviewAdded = useCallback(async () => {
    await refreshMemory()
  }, [refreshMemory])

  const detailId = selectedId

  if (error && !meta) {
    return (
      <div className="boot-error">
        <h1>🍜 HKU Bites</h1>
        <p>{error}</p>
        <p>
          Start the backend: <code>cd backend && .venv/bin/uvicorn app.main:app --port 8010</code>
        </p>
      </div>
    )
  }

  return (
    <div className="app">
      <Header
        llmConfig={llmConfig}
        onOpenConfig={() => setShowConfig(true)}
        onOpenMemory={() => {
          refreshMemory()
          setShowMemory(true)
        }}
        memoryCount={memory.suggestions.length + memory.reviews.length}
      />

      <div className="layout">
        <aside className="left-panel">
          <FilterChips
            filters={filters}
            onChange={setFilters}
            meta={meta}
            busy={busy}
            onReset={() => setFilters(EMPTY_FILTERS)}
          />
          <ChatBox
            thread={thread}
            busy={busy}
            onSend={sendChat}
            mode={mode}
            chatModeLabel={chatModeLabel}
            error={error}
          />
        </aside>

        <main className="right-panel">
          <MapView
            items={items}
            selectedId={detailId}
            onSelect={(id) => setSelectedId(id)}
            center={meta?.center}
          />
          <RestaurantList
            items={items}
            selectedId={detailId}
            onSelect={(id) => setSelectedId(id)}
            mode={mode}
            busy={busy}
          />
        </main>
      </div>

      {detailId && (
        <RestaurantDetail
          id={detailId}
          onClose={() => setSelectedId(null)}
          onReviewAdded={onReviewAdded}
        />
      )}
      {showConfig && (
        <LLMConfigModal
          current={llmConfig}
          onClose={() => setShowConfig(false)}
          onSaved={(cfg) => {
            setLlmConfig(cfg)
            setShowConfig(false)
          }}
        />
      )}
      {showMemory && (
        <MemoryPanel
          memory={memory}
          onClose={() => setShowMemory(false)}
          onCleared={refreshMemory}
        />
      )}
    </div>
  )
}
