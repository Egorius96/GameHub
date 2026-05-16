let timer: number | null = null

export function startPresencePing(token: string, game: string | null, intervalMs = 20000) {
  stopPresencePing()
  const ping = async () => {
    try {
      await fetch('/api/presence/ping', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ game: game ?? null }),
      })
    } catch {}
  }
  void ping()
  timer = window.setInterval(ping, intervalMs)
}

export function stopPresencePing() {
  if (timer) {
    window.clearInterval(timer)
    timer = null
  }
}

