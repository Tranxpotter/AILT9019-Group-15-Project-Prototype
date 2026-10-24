import { useEffect, useState } from 'react'
import { api } from '../api'

function Stars({ value, size = 20 }) {
  return (
    <span className="stars">
      {[1, 2, 3, 4, 5].map((n) => (
        <span
          key={n}
          className={`star ${n <= value ? 'on' : ''}`}
          style={{ fontSize: size }}
        >
          ★
        </span>
      ))}
    </span>
  )
}

export default function RestaurantDetail({ id, onClose }) {
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('photos')

  useEffect(() => {
    let alive = true
    api
      .restaurant(id)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null))
    return () => {
      alive = false
    }
  }, [id])

  if (!data) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal detail" onClick={(e) => e.stopPropagation()}>
          <p>Loading…</p>
        </div>
      </div>
    )
  }

  const hours = (data.opening || []).map((s) => `${s.days}: ${s.open}–${s.close}`).join('  ·  ')

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal detail" onClick={(e) => e.stopPropagation()}>
        <header className="detail-head">
          <img className="detail-hero" src={data.hero_image} alt={data.name} />
          <div className="detail-title">
            <h2>{data.name}</h2>
            <p>
              <span className="rating">★ {data.rating.toFixed(1)}</span> ({data.review_count}{' '}
              reviews) · {data.cuisine} · ${'$'.repeat(data.price_level)} · ~{data.avg_cost} HKD
            </p>
            <p className="dim">
              📍 {data.address} · 🚶 {data.walk_minutes} min walk from HKU · 🕐 {hours}
            </p>
            <p className="desc">{data.description}</p>
            <div className="chips wrap tiny">
              {data.tags?.map((t) => (
                <span key={t} className="chip static">
                  {t}
                </span>
              ))}
            </div>
          </div>
          <button className="btn ghost close" onClick={onClose}>
            ✕
          </button>
        </header>

        <nav className="tabs">
          {[
            ['photos', '🖼️ Photos'],
            ['menu', '📋 Menu'],
            ['reviews', '💬 Reviews'],
          ].map(([k, l]) => (
            <button key={k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>
              {l}
            </button>
          ))}
        </nav>

        {tab === 'photos' && (
          <div className="photos">
            <figure>
              <img src={data.interior_image} alt={`${data.name} interior`} />
              <figcaption>Interior (sample image with name)</figcaption>
            </figure>
            <figure>
              <img src={data.menu_image} alt={`${data.name} menu`} />
              <figcaption>Menu poster (generated)</figcaption>
            </figure>
          </div>
        )}

        {tab === 'menu' && (
          <div className="menu-tab">
            {(data.menu || []).map((item, i) => (
              <div key={i} className="menu-item">
                <div>
                  <span className="mi-name">{item.name}</span>
                  <span className="mi-cat">{item.category}</span>
                  <p className="mi-desc">{item.description}</p>
                </div>
                <strong className="mi-price">${item.price}</strong>
              </div>
            ))}
          </div>
        )}

        {tab === 'reviews' && (
          <div className="reviews-tab">
            <h4>Visitor reviews (synthetic)</h4>
            {(data.reviews || []).map((r, i) => (
              <div key={i} className="review">
                <strong>{r.user}</strong> <Stars value={r.rating} />
                <p>{r.comment}</p>
                <span className="dim">{r.date}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
