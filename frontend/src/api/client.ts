const API_BASE = (import.meta as any).env?.VITE_API_BASE ? String((import.meta as any).env.VITE_API_BASE) : '/api'

export class ApiHttpError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(message)
    this.name = 'ApiHttpError'
  }
}

function parseErrorBody(text: string): unknown {
  try {
    return JSON.parse(text) as unknown
  } catch {
    return { detail: text }
  }
}

export async function apiPost<T>(path: string, payload: unknown, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(payload)
  })
  if (!response.ok) {
    const text = await response.text()
    const body = parseErrorBody(text)
    const detail = (body as { detail?: unknown }).detail
    const msg =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object' && 'code' in (detail as object)
          ? String((detail as { code?: string }).code ?? 'Error')
          : `HTTP ${response.status}`
    throw new ApiHttpError(msg, response.status, body)
  }
  return response.json() as Promise<T>
}

export async function apiGet<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!response.ok) {
    const text = await response.text()
    throw new ApiHttpError(text || `HTTP ${response.status}`, response.status, parseErrorBody(text))
  }
  return response.json() as Promise<T>
}
