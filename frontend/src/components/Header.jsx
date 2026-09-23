export default function Header({ llmConfig, onOpenConfig, onOpenMemory, memoryCount }) {
  const configured = llmConfig?.configured
  const label = llmConfig?.provider ? llmConfig.provider : 'none'
  return (
    <header className="header">
      <div className="brand">
        <span className="brand-emoji">🍜</span>
        <div>
          <h1>HKU Bites</h1>
          <p>Restaurant recommender around HKU · synthetic demo data</p>
        </div>
      </div>
      <div className="header-actions">
        <span className={`llm-pill ${configured ? 'ok' : 'off'}`} title="LLM engine used for chat parsing & explanations">
          {configured ? `⚡ ${label}: ${llmConfig.model}` : '🐣 Demo mode (no LLM configured)'}
        </span>
        <button className="btn ghost" onClick={onOpenMemory}>
          🧠 Memory {memoryCount > 0 ? <span className="badge">{memoryCount}</span> : null}
        </button>
        <button className="btn primary" onClick={onOpenConfig}>
          ⚙️ LLM Config
        </button>
      </div>
    </header>
  )
}
