import { apiPost } from '../api/client'

let timer: number | null = null

export function startHeartbeat(token: string, gameKey: string) {
  stopHeartbeat()
  const tick = async () => {
    try {
      await apiPost('/profile/heartbeat', { game: gameKey, seconds: 10 }, token)
    } catch {
      // ignore network errors
    }
  }
  void tick()
  timer = window.setInterval(() => void tick(), 10_000)
}

export function stopHeartbeat() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

