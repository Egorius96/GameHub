import { onBeforeUnmount, ref } from 'vue'

export function useGameSocket(token: string, mode: string) {
  const state = ref<Record<string, any> | null>(null)
  const connected = ref(false)
  const gameOver = ref(false)

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/game?token=${encodeURIComponent(token)}&mode=${encodeURIComponent(mode)}`)

  ws.onopen = () => { connected.value = true }
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'state.tick') {
      state.value = msg.payload
      gameOver.value = !!msg.payload.game_over
    }
  }

  function move(direction: string, player = 1) {
    if (ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'input.move', direction, player }))
  }

  function ability(name: string) {
    if (ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'input.ability', ability: name }))
  }

  function restart() {
    if (ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'session.restart' }))
  }

  onBeforeUnmount(() => ws.close())

  return { state, connected, move, ability, restart, gameOver }
}
