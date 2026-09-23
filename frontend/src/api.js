const BASE = ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 300)}`)
  }
  return res.json()
}

export const api = {
  health: () => request('/api/health'),
  meta: () => request('/api/meta'),
  listRestaurants: (params = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && v.length === 0))
        qs.set(k, Array.isArray(v) ? v.join(',') : v)
    })
    return request(`/api/restaurants?${qs.toString()}`)
  },
  restaurant: (id) => request(`/api/restaurants/${id}`),
  chat: (payload) => request('/api/chat', { method: 'POST', body: JSON.stringify(payload) }),
  getLLMConfig: () => request('/api/llm-config'),
  llmProviders: () => request('/api/llm-config/providers'),
  saveLLMConfig: (cfg) => request('/api/llm-config', { method: 'PUT', body: JSON.stringify(cfg) }),
  testLLM: (cfg) => request('/api/llm-config/test', { method: 'POST', body: JSON.stringify(cfg) }),
  memory: () => request('/api/memory'),
  clearMemory: () => request('/api/memory/suggestions', { method: 'DELETE' }),
  addReview: (payload) => request('/api/reviews', { method: 'POST', body: JSON.stringify(payload) }),
}
