import { onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

export function useGameSocket(token: string, mode: string) {
  const { t } = useI18n()
  const state = ref<Record<string, any> | null>(null)
  const connected = ref(false)
  const gameOver = ref(false)
  const wsError = ref<string | null>(null)

  let ws: WebSocket | null = null
  let closedByUnmount = false
  let intentionalClose = false

  function connect() {
    if (!token?.trim()) {
      wsError.value = t('errors.unauthorized')
      return
    }
    wsError.value = null
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(
      `${proto}://${location.host}/ws/game?token=${encodeURIComponent(token)}&mode=${encodeURIComponent(mode)}`,
    )

    ws.onopen = () => {
      connected.value = true
      wsError.value = null
    }
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'state.error') {
          wsError.value = String(msg.message || t('errors.generic'))
          return
        }
        if (msg.type === 'state.tick') {
          wsError.value = null
          state.value = msg.payload
          gameOver.value = !!msg.payload.game_over
        }
      } catch {
        wsError.value = t('errors.generic')
      }
    }
    ws.onerror = () => {
      if (!state.value) {
        wsError.value = t('common.networkError')
      }
    }
    ws.onclose = () => {
      connected.value = false
      if (!closedByUnmount && !intentionalClose && !state.value) {
        wsError.value = wsError.value || t('common.networkError')
      }
      intentionalClose = false
    }
  }

  connect()

  function move(dx: number, dy: number, player = 1) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'input.move', dx, dy, player }))
  }

  function ability(name: string) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'input.ability', ability: name }))
  }

  function restart() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'session.restart' }))
  }

  function reconnect() {
    state.value = null
    gameOver.value = false
    wsError.value = null
    intentionalClose = true
    ws?.close()
    connect()
  }

  function disconnect() {
    intentionalClose = true
    ws?.close()
    ws = null
    connected.value = false
    state.value = null
    gameOver.value = false
    wsError.value = null
  }

  onBeforeUnmount(() => {
    closedByUnmount = true
    disconnect()
  })

  return { state, connected, wsError, move, ability, restart, reconnect, disconnect, gameOver }
}
