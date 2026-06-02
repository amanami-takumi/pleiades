export type SymbolRow = {
  id: number
  ticker: string
  name: string
  asset_type: string
  tag: string
  display_order: number
  currency: string | null
  exchange: string | null
  latest_close: number | null
  latest_date: string | null
  change_1d_percent: number | null
  per: number | null
  pbr: number | null
  roe: number | null
  market_cap: number | null
  dividend_yield: number | null
  last_error: string | null
  last_refreshed_at: string | null
}

export type PricePoint = {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  adj_close: number | null
  volume: number | null
  return_percent: number | null
}

export type HistoryResponse = {
  symbol: SymbolRow
  points: PricePoint[]
}

export type QueueResponse = {
  queued: number
  job_ids: number[]
}

export type RefreshJob = {
  id: number
  symbol_id: number | null
  ticker: string
  status: string
  error: string | null
  cancel_requested: boolean
  queued_at: string
  started_at: string | null
  finished_at: string | null
}

export type Purchase = {
  id: number
  symbol_id: number
  purchased_at: string
  amount: number
  quantity: number
  unit_price: number
  note: string | null
  created_at: string
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init
  })
  if (!response.ok) {
    const text = await response.text()
    let message = text
    try {
      const body = JSON.parse(text) as { detail?: string }
      message = body.detail || text
    } catch {
      message = text
    }
    throw new Error(message || `Request failed: ${response.status}`)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export function listSymbols() {
  return request<SymbolRow[]>('/api/symbols')
}

export function getHistory(id: number, range: string) {
  return request<HistoryResponse>(`/api/symbols/${id}/history?range=${range}`)
}

export function createSymbol(ticker: string, name?: string, assetType = 'stock', tag?: string) {
  return request<SymbolRow>('/api/symbols', {
    method: 'POST',
    body: JSON.stringify({ ticker, name, asset_type: assetType, tag })
  })
}

export function updateSymbol(id: number, payload: { tag?: string }) {
  return request<SymbolRow>(`/api/symbols/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function reorderSymbols(symbolIds: number[]) {
  return request<SymbolRow[]>('/api/symbols/order', {
    method: 'PUT',
    body: JSON.stringify({ symbol_ids: symbolIds })
  })
}

export function deleteSymbol(id: number) {
  return request<void>(`/api/symbols/${id}`, { method: 'DELETE' })
}

export function refreshAll() {
  return request<QueueResponse>('/api/refresh', { method: 'POST' })
}

export function refreshSymbol(id: number) {
  return request<QueueResponse>(`/api/symbols/${id}/refresh`, { method: 'POST' })
}

export function listRefreshJobs() {
  return request<RefreshJob[]>('/api/refresh/jobs?limit=50')
}

export function cancelRefreshJob(id: number) {
  return request<RefreshJob>(`/api/refresh/jobs/${id}/cancel`, { method: 'POST' })
}

export function listPurchases(symbolId: number) {
  return request<Purchase[]>(`/api/symbols/${symbolId}/purchases`)
}

export function createPurchase(symbolId: number, payload: { purchased_at: string; amount: number; quantity: number; note?: string }) {
  return request<Purchase>(`/api/symbols/${symbolId}/purchases`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function deletePurchase(id: number) {
  return request<void>(`/api/purchases/${id}`, { method: 'DELETE' })
}
