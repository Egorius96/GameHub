import { computed, onBeforeUnmount, ref } from 'vue'

export type TamagochiWorldPayload = {
  server_time: string
  world: {
    w: number
    h: number
    diamond_search_duration_sec?: number
    pet_play_duration_sec?: number
    pet_fight_duration_sec?: number
    pets: Array<any>
    events?: Array<any>
    pickups?: Array<any>
  }
  me: {
    pet: any | null
    neglect: any | null
    diamond_info?: {
      blocked: boolean
      avg_wellbeing?: number
      pace_percent: number
      estimated_cooldown_minutes: number | null
      toy_diamond_boost: boolean
      toy_diamond_minutes_left: number | null
      toy_passive_hours_left: number | null
      next_diamond_at?: string | null
      diamond_search_until?: string | null
    } | null
  }
}

export function useTamagochiSocket(token: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/tamagochi?token=${encodeURIComponent(token)}`)

  const connected = ref(false)
  const payload = ref<TamagochiWorldPayload | null>(null)
  const lastError = ref<string | null>(null)

  ws.onopen = () => {
    connected.value = true
  }
  ws.onclose = () => {
    connected.value = false
  }
  ws.onerror = () => {
    lastError.value = 'socket_error'
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'state.tick') {
        payload.value = msg.payload
      } else if (msg.type === 'state.error') {
        lastError.value = String(msg.message ?? 'error')
      }
    } catch {}
  }

  const pets = computed(() => payload.value?.world?.pets ?? [])
  const pickups = computed(() => payload.value?.world?.pickups ?? [])
  const events = computed(() => payload.value?.world?.events ?? [])
  const mePet = computed(() => payload.value?.me?.pet ?? null)

  onBeforeUnmount(() => {
    try {
      ws.close()
    } catch {}
  })

  return { connected, payload, pets, pickups, events, mePet, lastError }
}

