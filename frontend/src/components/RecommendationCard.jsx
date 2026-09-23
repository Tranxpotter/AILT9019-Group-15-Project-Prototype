export default function RecommendationCard({ item, index }) {
  return (
    <div className="rec-card">
      <img src={item.hero_image} alt={item.name} loading="lazy" />
      <div className="rec-body">
        <div className="rec-title">
          <span className="rec-index">{index}</span>
          <strong>{item.name}</strong>
          <span className="price">{'$'.repeat(item.price_level)}</span>
        </div>
        <div className="rec-meta">
          <span className="rating">★ {item.rating.toFixed(1)}</span>
          <span className="dim">· {item.cuisine}</span>
          <span className="dim">· {item.walk_minutes} min walk</span>
          <span className="dim">· ~{item.avg_cost} HKD</span>
        </div>
        {item.reason && <p className="rec-reason">💡 {item.reason}</p>}
        {item.tags?.length > 0 && (
          <div className="chips wrap tiny">
            {item.tags.slice(0, 3).map((t) => (
              <span key={t} className="chip static">
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
