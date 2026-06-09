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

export type TaskStatus = 'todo' | 'doing' | 'done'

export type TaskTag = {
  id: number
  name: string
  color: string
  hidden: boolean
  created_at: string
  updated_at: string
}

export type Task = {
  id: number
  title: string
  status: TaskStatus
  due_date: string | null
  duration_days: number | null
  tags: TaskTag[]
  details: string
  completed_at: string | null
  created_at: string
  updated_at: string
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

export function createPurchase(symbolId: number, payload: { purchased_at: string; amount: number; quantity?: number; note?: string }) {
  return request<Purchase>(`/api/symbols/${symbolId}/purchases`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function deletePurchase(id: number) {
  return request<void>(`/api/purchases/${id}`, { method: 'DELETE' })
}

export function listTaskTags() {
  return request<TaskTag[]>('/api/task-tags')
}

export function createTaskTag(payload: { name: string; color: string }) {
  return request<TaskTag>('/api/task-tags', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function updateTaskTag(id: number, payload: { name?: string; color?: string; hidden?: boolean }) {
  return request<TaskTag>(`/api/task-tags/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function deleteTaskTag(id: number) {
  return request<void>(`/api/task-tags/${id}`, { method: 'DELETE' })
}

export function listTasks() {
  return request<Task[]>('/api/tasks')
}

export function createTask(payload: {
  title: string
  status: TaskStatus
  due_date?: string | null
  duration_days?: number | null
  tag_ids: number[]
  details: string
}) {
  return request<Task>('/api/tasks', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function updateTask(
  id: number,
  payload: Partial<{
    title: string
    status: TaskStatus
    due_date: string | null
    duration_days: number | null
    tag_ids: number[]
    details: string
  }>
) {
  return request<Task>(`/api/tasks/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function deleteTask(id: number) {
  return request<void>(`/api/tasks/${id}`, { method: 'DELETE' })
}
