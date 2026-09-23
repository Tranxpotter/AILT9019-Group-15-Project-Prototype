import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

export default function LLMConfigModal({ current, onClose, onSaved }) {
  const [catalog, setCatalog] = useState({})
  const [form, setForm] = useState({
    provider: 'none',
    base_url: '',
    model: '',
    api_key: '',
    temperature: 0.3,
  })
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.llmProviders().then(setCatalog).catch(() => {})
    if (current) {
      setForm({
        provider: current.provider || 'none',
        base_url: current.base_url || '',
        model: current.model || '',
        api_key: current.api_key || '',
        temperature: current.temperature ?? 0.3,
      })
    }
  }, [current])

  const info = useMemo(() => catalog[form.provider] || {}, [catalog, form.provider])

  const pickProvider = (provider) => {
    const providerInfo = catalog[provider] || {}
    setForm((f) => ({
      ...f,
      provider,
      base_url: providerInfo.default_base || f.base_url,
      model: providerInfo.default_model || f.model,
      api_key: provider === 'ollama' || provider === 'custom' ? '' : f.api_key,
    }))
    setTestResult(null)
  }

  const test = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await api.testLLM(form))
    } catch (e) {
      setTestResult({ ok: false, detail: e.message })
    } finally {
      setTesting(false)
    }
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const saved = await api.saveLLMConfig(form)
      onSaved(saved)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal config" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>⚙️ LLM Configuration</h2>
          <p className="dim">
            The LLM parses your chat message into filters and writes the recommendations’ explanation.
            Set to <b>No LLM</b> for demo mode (built-in keyword parser).
          </p>
          <button className="btn ghost close" onClick={onClose}>
            ✕
          </button>
        </header>

        <div className="config-grid">
          <div className="field">
            <label>Provider</label>
            <select value={form.provider} onChange={(e) => pickProvider(e.target.value)}>
              {Object.entries(catalog).map(([key, v]) => (
                <option key={key} value={key}>
                  {v.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Model</label>
            <input
              placeholder={info.default_model || 'e.g. gpt-4o-mini, llama3.1, claude-…'}
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
            />
          </div>
          <div className="field wide">
            <label>
              Base URL {form.provider !== 'custom' ? '(optional override)' : '(required for custom endpoint)'}
            </label>
            <input
              placeholder={info.default_base || 'http://localhost:11434/v1'}
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
          </div>
          <div className="field">
            <label>API key</label>
            <input
              type="password"
              placeholder={info.needs_key ? 'sk-…' : 'not required for local'}
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Temperature: {form.temperature}</label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={form.temperature}
              onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) })}
            />
          </div>
        </div>

        <div className="config-actions">
          <button className="btn ghost" onClick={test} disabled={testing || !form.model || form.provider === 'none'}>
            {testing ? 'Testing…' : '🔌 Test connection'}
          </button>
          <button className="btn primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : '💾 Save configuration'}
          </button>
        </div>

        {testResult && (
          <div className={`test-result ${testResult.ok ? 'ok' : 'fail'}`}>
            {testResult.ok ? '✅' : '❌'} {testResult.detail}
          </div>
        )}
        {error && <div className="test-result fail">❌ {error}</div>}

        <div className="config-tips">
          <h4>Examples</h4>
          <ul>
            <li>
              <b>OpenAI</b>: model <code>gpt-4o-mini</code>, key from platform.openai.com
            </li>
            <li>
              <b>DeepSeek</b>: <code>deepseek-chat</code> at <code>https://api.deepseek.com/v1</code>
            </li>
            <li>
              <b>Ollama local</b>: run <code>ollama serve</code> + <code>ollama pull llama3.1</code>,
              base <code>http://localhost:11434/v1</code>, no key
            </li>
            <li>
              <b>Custom endpoint</b>: any OpenAI-compatible server (LM Studio, vLLM, OpenRouter, corporate proxy) —
              just give base URL + model (+key if needed)
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}
