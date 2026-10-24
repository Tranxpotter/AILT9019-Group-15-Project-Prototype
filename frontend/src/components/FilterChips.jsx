const MEALS = [
  ['', 'Any meal'],
  ['breakfast', '🥐 Breakfast'],
  ['lunch', '🍱 Lunch'],
  ['dinner', '🍽️ Dinner'],
  ['snack', '🍰 Snack'],
]
const PRICES = [
  [null, 'Any'],
  [1, '$'],
  [2, '$$'],
  [3, '$$$'],
]

export default function FilterChips({ filters, onChange, meta, busy, onReset }) {
  const set = (patch) => onChange({ ...filters, ...patch })
  const toggle = (key, v) => {
    const list = filters[key] || []
    set({ [key]: list.includes(v) ? list.filter((x) => x !== v) : [...list, v] })
  }

  return (
    <section className="filters card">
      <div className="card-head">
        <h2>
          Quick filters <span className="hint">(also used as chat context)</span>
        </h2>
        <button className="link" onClick={onReset} disabled={busy}>
          Reset
        </button>
      </div>

      <div className="filter-row">
        <label>Meal</label>
        <div className="chips">
          {MEALS.map(([v, l]) => (
            <button
              key={v || 'any'}
              className={`chip ${filters.meal === v ? 'on' : ''}`}
              onClick={() => set({ meal: v })}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-row">
        <label>Cost</label>
        <div className="chips">
          {PRICES.map(([v, l]) => (
            <button
              key={l}
              className={`chip ${filters.priceLevel === v ? 'on' : ''}`}
              onClick={() => set({ priceLevel: v })}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-row">
        <label>Cuisine</label>
        <div className="chips wrap">
          {(meta?.all_cuisines || []).map((c) => (
            <button
              key={c}
              className={`chip ${filters.cuisines.includes(c) ? 'on' : ''}`}
              onClick={() => toggle('cuisines', c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-row">
        <label>Dietary</label>
        <div className="chips wrap">
          {(meta?.dietary_options || []).map((d) => (
            <button
              key={d}
              className={`chip ${filters.dietary.includes(d) ? 'on' : ''}`}
              onClick={() => toggle('dietary', d)}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-row inline">
        <label>Eating at</label>
        <input
          type="time"
          value={filters.openAt}
          onChange={(e) => set({ openAt: e.target.value })}
        />
      </div>
    </section>
  )
}
