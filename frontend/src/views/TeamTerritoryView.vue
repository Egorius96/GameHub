<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { playSfx } from '../audio/sound'
import { startPresencePing, stopPresencePing } from '../telemetry/presence'
import { TEAM_TERRITORY_COMING_SOON } from '../config/features'

const GAME_KEY = 'team_territory'
const router = useRouter()
const auth = useAuthStore()

const roomId = ref('default')
const error = ref<string | null>(null)
const payload = ref<any>(null)
const wsRef = ref<WebSocket | null>(null)
const tickNow = ref(Date.now())
const mathAnswer = ref('')
const spellAnswer = ref('')
const reducedMotion = ref(
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
)

let tickTimer: number | null = null

const diamonds = computed(() => Number((auth.otherData as any)?.diamonds ?? 0))

const phase = computed(() => String(payload.value?.phase ?? 'lobby'))
const me = computed(() => payload.value?.me ?? {})
const isSpectator = computed(() => me.value?.role === 'spectator')
const g = computed(() => Math.max(1, Number(payload.value?.g ?? 10)))
const cells = computed(() => (Array.isArray(payload.value?.cells) ? payload.value.cells : []) as number[])
const teams = computed(() => (Array.isArray(payload.value?.teams) ? payload.value.teams : []) as any[])
const cfg = computed(() => payload.value?.config ?? {})
const challenge = computed(() => payload.value?.challenge ?? null)
const stall = computed(() => payload.value?.stall ?? {})

function teamStyle(teamId: number) {
  const t = teams.value.find((x: any) => Number(x?.id) === teamId)
  const hex = t?.hex ? String(t.hex) : '#666'
  return { background: teamId < 0 ? 'rgba(80,90,110,0.35)' : hex }
}

function connectWs() {
  error.value = null
  if (!auth.token) {
    error.value = 'Нет токена'
    return
  }
  wsRef.value?.close()
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/ws/team-territory?token=${encodeURIComponent(auth.token)}&room_id=${encodeURIComponent(roomId.value)}`
  const ws = new WebSocket(url)
  wsRef.value = ws
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'state' && msg.payload) {
        const prev = payload.value?.phase
        payload.value = msg.payload
        if (msg.payload.phase === 'finished' && prev !== 'finished') void auth.refreshProfile()
      } else if (msg.type === 'error') {
        error.value = String(msg.message ?? 'Ошибка')
      } else if (msg.type === 'buy_paint_result' && msg.payload && !msg.payload.ok) {
        error.value = String(msg.payload.error ?? 'Покупка не удалась')
      }
    } catch {
      /* ignore */
    }
  }
  ws.onclose = () => {
    wsRef.value = null
  }
}

function send(msg: Record<string, unknown>) {
  const ws = wsRef.value
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
}

function setReady(ready: boolean) {
  playSfx('button')
  send({ type: 'set_ready', ready })
}

function claimCell(idx: number) {
  if (isSpectator.value || phase.value !== 'playing') return
  playSfx('button')
  send({ type: 'claim', cell: idx })
}

function buyPaint() {
  playSfx('button')
  send({ type: 'buy_paint' })
}

function startChallenge() {
  playSfx('button')
  mathAnswer.value = ''
  spellAnswer.value = ''
  send({ type: 'challenge_start' })
}

function submitChallenge() {
  const ch = challenge.value
  if (!ch) return
  const mode = Number(ch.mode)
  if (mode === 1) {
    send({ type: 'challenge_submit', answer: mathAnswer.value })
    mathAnswer.value = ''
  } else if (mode === 2) {
    send({ type: 'challenge_submit', answer: spellAnswer.value })
    spellAnswer.value = ''
  }
}

function tapCircle(label: number) {
  const ch = challenge.value
  if (!ch || Number(ch.mode) !== 3) return
  const gap = ch.next_round_not_before ? Date.parse(String(ch.next_round_not_before)) : 0
  if (gap && Date.now() < gap) return
  send({ type: 'challenge_submit', label })
}

function resetLobby() {
  playSfx('button')
  send({ type: 'reset_to_lobby' })
}

function setNumTeams(n: number) {
  send({ type: 'set_num_teams', num_teams: n })
}

const msToNextTick = computed(() => {
  void tickNow.value
  const iso = payload.value?.next_tick_at
  if (!iso) return null
  const t = Date.parse(String(iso))
  if (!Number.isFinite(t)) return null
  return Math.max(0, t - Date.now())
})

const msStallLeft = computed(() => {
  void tickNow.value
  const iso = stall.value?.deadline_at
  if (!iso) return null
  const t = Date.parse(String(iso))
  if (!Number.isFinite(t)) return null
  return Math.max(0, t - Date.now())
})

onMounted(() => {
  if (TEAM_TERRITORY_COMING_SOON) return
  startPresencePing(auth.token, GAME_KEY)
  connectWs()
  tickTimer = window.setInterval(() => {
    tickNow.value = Date.now()
  }, 250)
})

onBeforeUnmount(() => {
  stopPresencePing()
  if (tickTimer) window.clearInterval(tickTimer)
  wsRef.value?.close()
})
</script>

<template>
  <div v-if="TEAM_TERRITORY_COMING_SOON" class="tt-wip">
    <header class="tt-header">
      <button type="button" class="btn tt-back" @click="router.push('/games')">← Хаб</button>
      <h1 class="tt-title">Team Territory</h1>
    </header>
    <div class="tt-wip-card card">
      <h2 class="tt-wip-title">Игра в разработке</h2>
      <p class="tt-wip-text">Team Territory пока недоступна.</p>
      <button type="button" class="btn btn-primary" @click="router.push('/games')">Вернуться в хаб</button>
    </div>
  </div>
  <div v-else class="tt-root">
    <header class="tt-header">
      <button type="button" class="btn tt-back" @click="router.push('/games')">← Хаб</button>
      <h1 class="tt-title">Team Territory</h1>
      <div class="tt-wallet">💎 {{ diamonds }}</div>
    </header>

    <div v-if="cfg.debug_solo_lobby" class="tt-debug">DEBUG: solo lobby (dev)</div>
    <div v-if="error" class="tt-err">{{ error }}</div>

    <section v-if="isSpectator" class="tt-banner">
      Наблюдатель: закраска недоступна. Дождитесь следующего матча.
      <span v-if="me.spectator_queue_position"> Очередь: {{ me.spectator_queue_position }}</span>
    </section>

    <section v-if="phase === 'lobby'" class="tt-lobby card">
      <h2>Лобби</h2>
      <p class="muted">Комната: <strong>{{ roomId }}</strong></p>
      <label class="tt-field">
        <span>ID комнаты</span>
        <input v-model="roomId" class="tt-input" @change="connectWs" />
      </label>
      <div class="tt-row">
        <span>Команд:</span>
        <button type="button" class="btn" @click="setNumTeams(2)">2</button>
        <button type="button" class="btn" @click="setNumTeams(3)">3</button>
        <button type="button" class="btn" @click="setNumTeams(4)">4</button>
      </div>
      <div class="tt-players">
        <div v-for="(slot, u) in payload?.players ?? {}" :key="u" class="tt-pl">
          <span>{{ u }}</span>
          <span class="muted">команда {{ (slot?.team_id ?? 0) + 1 }}</span>
          <span v-if="slot?.ready" class="ok">готов</span>
        </div>
      </div>
      <button type="button" class="btn btn-primary tt-ready" @click="setReady(true)">Готов</button>
    </section>

    <section v-if="phase === 'playing' || phase === 'finished'" class="tt-match">
      <div class="tt-hud card">
        <div>Тик #{{ payload?.tick_index ?? 0 }}</div>
        <div v-if="msToNextTick != null" class="tt-timer">До закрытия тика: {{ Math.ceil(msToNextTick / 1000) }} с</div>
        <div>Краска: <strong>{{ me.paint ?? 0 }}</strong> / {{ cfg.paint_max ?? 10 }}</div>
        <div class="muted">Чужая краска (сумма): {{ payload?.opponent_ink?.sum ?? 0 }}</div>
        <div v-if="stall.phase === 'warn' && msStallLeft != null" class="tt-stall">
          Нет действий — ничья через {{ Math.ceil(msStallLeft / 1000) }} с
        </div>
        <div class="tt-actions">
          <button type="button" class="btn" :disabled="isSpectator" @click="buyPaint">
            Купить +{{ cfg.bundle }} ({{ cfg.diamond_cost }} 💎)
          </button>
          <button type="button" class="btn" :disabled="isSpectator || !!challenge" @click="startChallenge">Challenge</button>
        </div>
      </div>

      <div
        class="tt-grid-wrap card"
        :class="{ 'tt-grid-wrap--dense': g > 12 }"
      >
        <div class="tt-grid" :style="{ gridTemplateColumns: `repeat(${g}, 1fr)` }">
          <button
            v-for="(c, i) in cells"
            :key="i"
            type="button"
            class="tt-cell"
            :class="{ pulse: !reducedMotion && c < 0 }"
            :style="teamStyle(Number(c))"
            :disabled="isSpectator || phase !== 'playing' || c >= 0"
            @click="claimCell(i)"
          />
        </div>
      </div>

      <div v-if="phase === 'finished'" class="tt-result card">
        <h2>Матч окончен</h2>
        <p>{{ payload?.finish_reason }}</p>
        <p>Счёт по командам: {{ JSON.stringify(payload?.scores ?? {}) }}</p>
        <p v-if="(payload?.winning_team_ids ?? []).length">Победили команды: {{ payload?.winning_team_ids?.map((x: number) => x + 1).join(', ') }}</p>
        <button type="button" class="btn btn-primary" @click="resetLobby">В лобби</button>
      </div>
    </section>

    <div v-if="challenge" class="tt-ch-overlay" @click.self>
      <div class="tt-ch card" :class="{ 'tt-ch--nomotion': reducedMotion }">
        <h3>Challenge · режим {{ challenge.mode }}</h3>
        <p v-if="challenge.round_deadline_at" class="muted">
          Дедлайн раунда: {{ new Date(challenge.round_deadline_at).toLocaleTimeString() }}
        </p>
        <template v-if="Number(challenge.mode) === 1">
          <p class="tt-prompt">{{ challenge.prompt }}</p>
          <input v-model="mathAnswer" class="tt-input" type="number" @keyup.enter="submitChallenge" />
          <button type="button" class="btn btn-primary" @click="submitChallenge">Ответить</button>
        </template>
        <template v-else-if="Number(challenge.mode) === 2">
          <p class="tt-prompt">{{ challenge.prompt }}</p>
          <input v-model="spellAnswer" maxlength="1" class="tt-input" @keyup.enter="submitChallenge" />
          <button type="button" class="btn btn-primary" @click="submitChallenge">Буква</button>
        </template>
        <template v-else-if="Number(challenge.mode) === 3">
          <p>Следующий: <strong>{{ challenge.sequence_next }}</strong></p>
          <div class="tt-circles">
            <button
              v-for="c in challenge.circles ?? []"
              :key="c.id"
              type="button"
              class="tt-circle"
              @click="tapCircle(Number(c.label))"
            >
              {{ c.label }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tt-wip {
  min-height: 100vh;
  background: linear-gradient(165deg, #0f1320 0%, #1a1f35 50%, #12182a 100%);
  color: #e8ecf7;
  padding: 16px;
  font-family: system-ui, sans-serif;
}
.tt-wip-card {
  max-width: 440px;
  margin: 24px auto 0;
  text-align: center;
}
.tt-wip-title {
  margin: 0 0 12px 0;
  font-size: 1.35rem;
}
.tt-wip-text {
  margin: 0 0 20px 0;
  line-height: 1.5;
  opacity: 0.92;
}
.tt-root {
  min-height: 100vh;
  background: linear-gradient(165deg, #0f1320 0%, #1a1f35 50%, #12182a 100%);
  color: #e8ecf7;
  padding: 16px;
  font-family: system-ui, sans-serif;
}
.tt-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.tt-title {
  flex: 1;
  margin: 0;
  font-size: 1.35rem;
}
.tt-wallet {
  font-weight: 700;
}
.tt-debug {
  background: #b71c1c;
  color: #fff;
  padding: 8px 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  font-weight: 600;
}
.tt-err {
  color: #ffcdd2;
  margin-bottom: 8px;
}
.tt-banner {
  background: rgba(255, 193, 7, 0.15);
  border: 1px solid rgba(255, 193, 7, 0.4);
  padding: 10px 12px;
  border-radius: 10px;
  margin-bottom: 12px;
}
.card {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  padding: 14px;
  margin-bottom: 12px;
}
.muted {
  opacity: 0.75;
  font-size: 0.9rem;
}
.ok {
  color: #a5d6a7;
  margin-left: 8px;
}
.btn {
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.08);
  color: inherit;
  padding: 8px 14px;
  border-radius: 10px;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.btn-primary {
  background: linear-gradient(135deg, #3949ab, #5c6bc0);
  border-color: transparent;
}
.tt-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 10px 0;
}
.tt-input {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
}
.tt-players {
  margin: 12px 0;
}
.tt-pl {
  display: flex;
  gap: 10px;
  padding: 4px 0;
}
.tt-hud {
  display: grid;
  gap: 6px;
}
.tt-timer {
  font-size: 1.25rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.tt-stall {
  color: #ffab91;
  font-weight: 600;
}
.tt-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.tt-grid-wrap {
  overflow: auto;
  max-height: 70vh;
}
.tt-grid-wrap--dense .tt-cell {
  min-width: 22px;
  min-height: 22px;
}
.tt-grid {
  display: grid;
  gap: 3px;
}
.tt-cell {
  aspect-ratio: 1;
  min-width: 28px;
  min-height: 28px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.25);
  cursor: pointer;
  transition: transform 0.15s ease-out, box-shadow 0.15s;
}
.tt-cell:disabled {
  cursor: default;
  opacity: 0.85;
}
.tt-cell:not(:disabled):hover {
  transform: scale(1.04);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.35);
}
@keyframes tt-pulse {
  50% {
    filter: brightness(1.15);
  }
}
.tt-cell.pulse {
  animation: tt-pulse 1.8s ease-in-out infinite;
}
.tt-ch-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  padding: 16px;
}
.tt-ch {
  max-width: 420px;
  width: 100%;
}
.tt-ch--nomotion .tt-circle {
  transition: none;
}
.tt-prompt {
  font-size: 1.4rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.tt-circles {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  justify-content: center;
}
.tt-circle {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  font-weight: 800;
  font-size: 1.1rem;
  border: 2px solid rgba(255, 255, 255, 0.35);
  background: rgba(30, 40, 70, 0.9);
  color: inherit;
  cursor: pointer;
  transition: transform 0.12s ease-out;
}
.tt-circle:active {
  transform: scale(0.95);
}
@media (prefers-reduced-motion: reduce) {
  .tt-cell.pulse {
    animation: none;
  }
  .tt-cell:not(:disabled):hover {
    transform: none;
  }
}
</style>
