export function mapApiError(detail: unknown, t: (key: string, params?: Record<string, unknown>) => string): string {
  if (typeof detail === 'string') return detail
  if (!detail || typeof detail !== 'object') return t('errors.generic')
  const d = detail as { code?: string; params?: Record<string, unknown>; message?: string }
  if (d.code) {
    const key = `errors.${d.code}`
    const translated = t(key, d.params ?? {})
    if (translated !== key) return translated
  }
  if (d.message) return d.message
  return t('errors.generic')
}
