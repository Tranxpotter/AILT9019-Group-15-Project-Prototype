import { useEffect, useRef, useState } from 'react'
import RecommendationCard from './RecommendationCard'

const EXAMPLES = [
  'Cheap lunch near campus under 10 minutes walk',
  'Dim sum for breakfast',
  'Halal vegetarian dinner with friends',
  'Something cheap and sweet open after 11pm',
]

const RELAX_LABELS = {
  price_level: 'price',
  dietary: 'dietary',
  allergens: 'allergens',
  cuisines: 'cuisine',
  preferences: 'preference',
  open_at: 'opening time',
  meal: 'meal',
}

function StructuredBadge({ structured }) {
  if (!structured) return null
  const parts = []
  if (structured.meal) parts.push(`meal: ${structured.meal}`)
  if (structured.cuisines?.length) parts.push(`cuisines: ${structured.cuisines.join(', ')}`)
  if (structured.dish_intent?.length) parts.push(`dish: ${structured.dish_intent.join('/')}`)
  if (structured.texture?.length) parts.push(`texture: ${structured.texture.join('/')}`)
  if (structured.vibe?.length) parts.push(`vibe: ${structured.vibe.join('/')}`)
  if (structured.price_level) parts.push(`price: ${'$'.repeat(structured.price_level)}`)
  if (structured.open_at) parts.push(`open at ${structured.open_at}`)
  if (structured.dietary?.length) parts.push(`dietary: ${structured.dietary.join('+')}`)
  if (structured.allergens?.length) parts.push(`allergens: ${structured.allergens.join('+')}`)
  if (!parts.length) return null
  return <div className="structured-badge">parsed → {parts.join(' · ')}</div>
}

export default function ChatBox({ thread, busy, onSend, mode, chatModeLabel, error }) {
  const [text, setText] = useState('')
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [thread])

  const send = () => {
    onSend(text)
    setText('')
    inputRef.current?.focus()
  }

  return (
    <section className="chat card">
      <div className="card-head">
        <h2>
          💬 Ask the recommender{' '}
          <span className="hint">
            {mode === 'chat' ? chatModeLabel : 'natural language or send quick filters'}
          </span>
        </h2>
      </div>

      <div className="chat-thread" ref={scrollRef}>
        {thread.length === 0 && (
          <div className="chat-empty">
            <p>Try one of these:</p>
            <div className="chips wrap">
              {EXAMPLES.map((e) => (
                <button key={e} className="chip" onClick={() => onSend(e)}>
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {thread.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="msg user">
              {m.text}
            </div>
          ) : (
            <div key={i} className="msg assistant">
              {m.status === 'no_match' && (
                <div className="no-match-badge">🚫 No suitable restaurant found</div>
              )}
              {m.soft_fallback && (
                <div className="soft-fallback-badge">
                  ⚠️ No exact preference match
                  {m.unmet_soft?.length ? ` (${m.unmet_soft.join(', ')})` : ''} —
                  showing closest hard-constraint options
                </div>
              )}
              {m.relaxed?.length > 0 && (
                <div className="relaxed-badge">
                  ⚠️ Relaxed filter(s):{' '}
                  {m.relaxed.map((f) => RELAX_LABELS[f] || f).join(', ')}
                </div>
              )}
              {m.selection_mode === 'llm_rerank' && (
                <div className="selection-badge">
                  🎯 LLM re-ranked {m.candidate_count} candidate
                  {m.candidate_count === 1 ? '' : 's'}
                </div>
              )}
              {m.selection_mode === 'fallback' && (
                <div className="selection-badge fallback" title={m.selection_note || ''}>
                  ↩︎ Deterministic ranking (LLM selection unavailable)
                </div>
              )}
              <p className={`summary ${m.mode === 'demo' ? 'demo' : ''}`}>{m.summary}</p>
              {m.mode && <StructuredBadge structured={m.structured} />}
              {m.picks?.length > 0 && (
                <div className="picks">
                  {m.picks.map((p, j) => (
                    <RecommendationCard key={p.id} item={p} index={j + 1} />
                  ))}
                </div>
              )}
            </div>
          ),
        )}
        {busy && (
          <div className="msg assistant typing">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
            <em> asking {mode === 'chat' ? 'the recommender' : 'the parser'}…</em>
          </div>
        )}
        {error && <div className="chat-error">⚠️ {error}</div>}
      </div>

      <div className="chat-input">
        <textarea
          ref={inputRef}
          rows={2}
          placeholder="e.g. I want a cheap healthy lunch today, halal if possible…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          disabled={busy}
        />
        <button className="btn primary send" onClick={send} disabled={busy || !text.trim()}>
          {busy ? '…' : '➤'}
        </button>
      </div>
    </section>
  )
}
