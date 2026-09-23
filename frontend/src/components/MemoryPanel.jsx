import { useState } from 'react'

export default function MemoryPanel({ memory, onClose, onCleared }) {
  const [tab, setTab] = useState('suggestions')
  const [confirm, setConfirm] = useState(false)

  const clear = async () => {
    await fetch('/api/memory/suggestions', { method: 'DELETE', headers: { 'Content-Type': 'application/json' } })
    setConfirm(false)
    onCleared()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal memory" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>🧠 Memory</h2>
          <p className="dim">What the app has suggested to you, plus your own reviews.</p>
          <button className="btn ghost close" onClick={onClose}>
            ✕
          </button>
        </header>
        <nav className="tabs">
          <button className={`tab ${tab === 'suggestions' ? 'on' : ''}`} onClick={() => setTab('suggestions')}>
            Previously suggested ({memory.suggestions.length})
          </button>
          <button className={`tab ${tab === 'reviews' ? 'on' : ''}`} onClick={() => setTab('reviews')}>
            My reviews ({memory.reviews.length})
          </button>
        </nav>

        {tab === 'suggestions' && (
          <div className="mem-list">
            {memory.suggestions.length === 0 && (
              <p className="dim pad">Nothing suggested yet — ask the recommender once and it will remember.</p>
            )}
            {memory.suggestions.map((s) => (
              <div key={s.id} className="mem-row">
                <img src={s.hero_image} alt="" />
                <div>
                  <strong>{s.restaurant_name}</strong>
                  <p className="dim">
                    asked: “{s.query}” · {s.created_at?.slice(0, 10)}
                  </p>
                  {s.reason && <p className="rec-reason">💡 {s.reason}</p>}
                </div>
              </div>
            ))}
            {memory.suggestions.length > 0 && (
              <div className="mem-actions">
                {confirm ? (
                  <>
                    <span>Clear all suggestion history?</span>
                    <button className="btn danger" onClick={clear}>
                      Yes, clear
                    </button>
                    <button className="btn ghost" onClick={() => setConfirm(false)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button className="btn ghost" onClick={() => setConfirm(true)}>
                    🧹 Clear suggestion history
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {tab === 'reviews' && (
          <div className="mem-list">
            {memory.reviews.length === 0 && (
              <p className="dim pad">No reviews yet. Open a restaurant and rate it!</p>
            )}
            {memory.reviews.map((r) => (
              <div key={r.id} className="mem-row">
                <img src={r.hero_image} alt="" />
                <div>
                  <strong>
                    {r.restaurant_name} <span className="rating">★ {r.rating}/5</span>
                  </strong>
                  <p>{r.comment || '—'}</p>
                  <p className="dim">{r.created_at?.slice(0, 10)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
