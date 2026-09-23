export default function RestaurantList({ items, selectedId, onSelect, mode, busy }) {
  return (
    <section className="list card">
      <div className="card-head">
        <h2>
          {mode === 'chat' ? '🤖 Suggested for you' : '🗺️ On the map'}
          <span className="hint">({items.length})</span>
        </h2>
      </div>
      {busy && <div className="list-busy">Loading…</div>}
      {!busy && items.length === 0 && (
        <div className="list-empty">No matches — try relaxing a filter or describing differently.</div>
      )}
      <div className="list-items">
        {items.map((item, i) => (
          <button
            key={item.id}
            className={`list-item ${selectedId === item.id ? 'active' : ''}`}
            onClick={() => onSelect(item.id)}
          >
            <img src={item.hero_image} alt="" loading="lazy" />
            <div className="li-body">
              <div className="rec-title">
                <strong>{item.name}</strong>
                <span className="price">{'$'.repeat(item.price_level)}</span>
              </div>
              <div className="rec-meta">
                <span className="rating">★ {item.rating.toFixed(1)}</span>
                <span className="dim">· {item.cuisine}</span>
                <span className="dim">· {item.walk_minutes} min</span>
              </div>
              {item.reason && <p className="rec-reason">{item.reason}</p>}
            </div>
            <span className="li-index">{i + 1}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
