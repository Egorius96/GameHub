const STORAGE_KEY = 'gamehub_auth_v1'

export interface StoredAuth {
  token: string
  username: string
  otherData: Record<string, unknown>
}

export function loadStoredAuth(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const data = JSON.parse(raw) as Partial<StoredAuth>
    if (!data.token || typeof data.token !== 'string') return null
    return {
      token: data.token,
      username: typeof data.username === 'string' ? data.username : '',
      otherData:
        data.otherData && typeof data.otherData === 'object' && !Array.isArray(data.otherData)
          ? (data.otherData as Record<string, unknown>)
          : {},
    }
  } catch {
    return null
  }
}

export function saveStoredAuth(payload: StoredAuth): void {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        token: payload.token,
        username: payload.username,
        otherData: payload.otherData,
      }),
    )
  } catch {
    /* quota / private mode */
  }
}

export function clearStoredAuth(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
