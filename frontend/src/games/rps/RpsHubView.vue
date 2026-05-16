<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { playSfx } from '../../audio/sound'
import { startPresencePing, stopPresencePing } from '../../telemetry/presence'
import RpsCardBoard, { type RpsMove, type RpsRoundVerdict } from './RpsCardBoard.vue'
import RpsMatchEndModal from './RpsMatchEndModal.vue'

const GAME_KEY = 'rps_game'
const router = useRouter()
const auth = useAuthStore()

type Mode = 'menu' | 'robot' | 'online_lobby' | 'online_room'
const mode = ref<Mode>('menu')
const onlineRoomId = ref(0)

const rooms = ref<Array<{ room_id: number; occupancy: number }>>([])
let roomsTimer: number | null = null

const robotSession = ref('')
const robotBusy = ref(false)
const robotLog = ref<string[]>([])
const playerWins = ref(0)
const robotWins = ref(0)
const robotFinished = ref(false)
const robotWonMatch = ref(false)
const robotError = ref('')
const robotPhase = ref<'picking' | 'revealing'>('picking')
const robotSelected = ref<RpsMove | null>(null)
const robotPickSec = ref(5)
const robotRevealSec = ref(0)
const robotOppMove = ref<RpsMove | null>(null)
const robotHighlight = ref<'player' | 'opponent' | 'tie' | null>(null)
const showRobotEndModal = ref(false)
const robotRewardPending = ref(false)
const diamondHudRef = ref<HTMLElement | null>(null)
type DiamondFlight = { id: string; x0: number; y0: number; x1: number; y1: number }
const diamondFlights = ref<DiamondFlight[]>([])
const showOnlineEndModal = ref(false)
let robotPollTimer: number | null = null
let robotRoundLogKey = ''
let robotRewardLogged = false
let onlineEndHandled = false

let ws: WebSocket | null = null
let onlineDiamondRefreshTimer: number | null = null
const roomState = ref<any>(null)
const onlineError = ref('')
const chatDraft = ref('')
const betAmount = ref(3)

const diamonds = computed(() => Number((auth.otherData as any).diamonds ?? 0))
const stakeLine = computed(() => {
  const s = roomState.value?.stakes as Record<string, number> | undefined
  if (!s || typeof s !== 'object') return '—'
  return Object.entries(s)
    .map(([u, v]) => `${u}: ${v}`)
    .join(' · ')
})

const moveLabel: Record<string, string> = {
  rock: 'Камень',
  paper: 'Бумага',
  scissors: 'Ножницы',
}

function oppMovesMap(move: string | null | undefined): Partial<Record<RpsMove, RpsMove | null>> {
  if (!move) return {}
  const m = move as RpsMove
  return { [m]: m }
}

const robotOppMoves = computed(() => oppMovesMap(robotOppMove.value))
const robotRoundVerdict = computed((): RpsRoundVerdict => {
  if (robotPhase.value !== 'revealing') return null
  if (robotHighlight.value === 'player') return 'win'
  if (robotHighlight.value === 'opponent') return 'lose'
  if (robotHighlight.value === 'tie') return 'tie'
  return null
})
const robotBoardRevealed = computed(() => robotPhase.value === 'revealing')
const robotBoardDisabled = computed(
  () => robotBusy.value || !robotSession.value || robotFinished.value || robotPhase.value !== 'picking'
)

const onlineRoundPhase = computed(() => (roomState.value?.round_phase as string) || 'pick')
const onlineSelected = computed(() => (roomState.value?.your_choice as RpsMove | null) || null)
const onlineOppMove = computed(() => (roomState.value?.opponent_choice as RpsMove | null) || null)
const onlineBoardRevealed = computed(
  () => roomState.value?.phase === 'playing' && onlineRoundPhase.value === 'reveal'
)
const onlinePickSec = computed(() => Math.ceil(Number(roomState.value?.pick_seconds_left ?? 0)))
const onlineRevealSec = computed(() => Math.ceil(Number(roomState.value?.reveal_seconds_left ?? 0)))
const onlineOppMoves = computed(() => oppMovesMap(onlineOppMove.value))
const onlineBoardDisabled = computed(
  () => roomState.value?.phase !== 'playing' || onlineRoundPhase.value !== 'pick'
)
const onlineHighlight = computed((): 'player' | 'opponent' | 'tie' | null => {
  const lr = roomState.value?.last_round
  if (!lr || onlineRoundPhase.value !== 'reveal') return null
  const you = roomState.value?.you as string
  if (lr.winner === you) return 'player'
  if (lr.winner && lr.winner !== you) return 'opponent'
  return 'tie'
})
const onlineRoundVerdict = computed((): RpsRoundVerdict => {
  if (onlineRoundPhase.value !== 'reveal') return null
  const h = onlineHighlight.value
  if (h === 'player') return 'win'
  if (h === 'opponent') return 'lose'
  if (h === 'tie') return 'tie'
  return null
})
const onlineOpponentLabel = computed(() => {
  const you = roomState.value?.you as string
  return (roomState.value?.players as string[])?.find((p: string) => p !== you) ?? 'Соперник'
})
const onlineMatchWon = computed(() => {
  const lr = roomState.value?.last_round
  if (!lr?.match_over) return false
  return lr.match_winner === roomState.value?.you
})
const onlineEndScores = computed(() => {
  const you = roomState.value?.you as string
  const w = roomState.value?.wins as Record<string, number> | undefined
  if (!you || !w) return { player: 0, opponent: 0 }
  const opp = onlineOpponentLabel.value
  return { player: Number(w[you] ?? 0), opponent: Number(w[opp] ?? 0) }
})

const PICK_TOTAL_SEC = 5

const robotTimerSec = computed(() =>
  robotPhase.value === 'picking' ? robotPickSec.value : robotRevealSec.value
)
const robotTimerLabel = computed(() => (robotPhase.value === 'picking' ? 'Выбор' : 'Итог раунда'))
const robotTimerProgress = computed(() =>
  Math.max(0, Math.min(100, (robotTimerSec.value / PICK_TOTAL_SEC) * 100))
)
const robotTimerUrgent = computed(() => robotTimerSec.value > 0 && robotTimerSec.value <= 3)

const onlineTimerSec = computed(() =>
  onlineRoundPhase.value === 'pick' ? onlinePickSec.value : onlineRevealSec.value
)
const onlineTimerLabel = computed(() => (onlineRoundPhase.value === 'pick' ? 'Выбор' : 'Итог раунда'))
const onlineTimerProgress = computed(() =>
  Math.max(0, Math.min(100, (onlineTimerSec.value / PICK_TOTAL_SEC) * 100))
)
const onlineTimerUrgent = computed(() => onlineTimerSec.value > 0 && onlineTimerSec.value <= 3)

async function loadRooms() {
  try {
    const resp = await fetch('/api/rps/rooms', { headers: { Authorization: `Bearer ${auth.token}` } })
    const data = await resp.json().catch(() => ({}))
    if (resp.ok && Array.isArray(data.rooms)) rooms.value = data.rooms
  } catch {}
}

function exitHub() {
  playSfx('button')
  disconnectWs()
  if (roomsTimer) {
    window.clearInterval(roomsTimer)
    roomsTimer = null
  }
  router.push('/games')
}

function goMenu() {
  playSfx('button')
  stopRobotPoll()
  disconnectWs()
  if (roomsTimer) {
    window.clearInterval(roomsTimer)
    roomsTimer = null
  }
  mode.value = 'menu'
  onlineError.value = ''
  robotError.value = ''
}

function openRobot() {
  playSfx('button')
  mode.value = 'robot'
  resetRobotUi()
}

function openOnlineLobby() {
  playSfx('button')
  if (roomsTimer) {
    window.clearInterval(roomsTimer)
    roomsTimer = null
  }
  mode.value = 'online_lobby'
  void loadRooms()
  roomsTimer = window.setInterval(() => void loadRooms(), 2000)
}

function stopRobotPoll() {
  if (robotPollTimer) {
    window.clearInterval(robotPollTimer)
    robotPollTimer = null
  }
}

function resetRobotUi() {
  stopRobotPoll()
  robotSession.value = ''
  robotLog.value = []
  playerWins.value = 0
  robotWins.value = 0
  robotFinished.value = false
  robotWonMatch.value = false
  robotError.value = ''
  robotPhase.value = 'picking'
  robotSelected.value = null
  robotPickSec.value = 5
  robotRevealSec.value = 0
  showRobotEndModal.value = false
  robotRewardPending.value = false
  robotOppMove.value = null
  robotHighlight.value = null
  robotRoundLogKey = ''
  robotRewardLogged = false
}

function applyRobotState(data: Record<string, any>) {
  const tick = data.tick as Record<string, any> | undefined
  const src = tick ? { ...data, ...tick } : data
  robotPhase.value = (src.phase as 'picking' | 'revealing') || 'picking'
  robotPickSec.value = Math.max(0, Math.ceil(Number(src.pick_seconds_left ?? 0)))
  robotRevealSec.value = Math.max(0, Math.ceil(Number(src.reveal_seconds_left ?? 0)))
  if (src.pending_move) robotSelected.value = src.pending_move as RpsMove
  playerWins.value = Number(src.player_wins ?? playerWins.value)
  robotWins.value = Number(src.robot_wins ?? robotWins.value)
  robotFinished.value = !!src.finished
  const lr = src.last_round as Record<string, any> | null | undefined
  if (robotPhase.value === 'revealing' && lr) {
    robotOppMove.value = (lr.robot as RpsMove) || null
    if (lr.player) robotSelected.value = lr.player as RpsMove
    const ws = String(lr.winner_side ?? '')
    const forfeit = !!lr.forfeit
    if (ws === 'player') robotHighlight.value = 'player'
    else if (ws === 'robot') robotHighlight.value = 'opponent'
    else robotHighlight.value = 'tie'
    if (forfeit && !lr.player) robotHighlight.value = 'opponent'
  } else if (robotPhase.value === 'picking') {
    robotOppMove.value = null
    robotHighlight.value = null
    if (!src.pending_move) robotSelected.value = null
  }
  if (src.finished && !robotRewardLogged) {
    robotRewardLogged = true
    robotWonMatch.value = !!src.player_won_match
    const reward = src.reward as Record<string, any> | undefined
    robotRewardPending.value = Boolean(
      robotWonMatch.value && reward && !reward.granted && Number(reward.wait_seconds ?? 0) > 0
    )
    showRobotEndModal.value = true
    if (robotWonMatch.value) {
      window.setTimeout(() => launchDiamondFlyFromCenter(), 500)
    }
    if (reward?.lost) robotLog.value.push('Партия проиграна.')
    if (reward?.granted) {
      void auth.refreshProfile()
    } else if (robotRewardPending.value) {
      const waitMs = Math.ceil(Number(reward?.wait_seconds ?? 1) * 1000) + 400
      window.setTimeout(() => void claimRobot(), waitMs)
    }
  }
  const ws = String((tick ?? src).winner_side ?? '')
  if (ws && robotPhase.value === 'revealing') {
    const key = `${playerWins.value}-${robotWins.value}-${ws}`
    if (key !== robotRoundLogKey) {
      robotRoundLogKey = key
      if (ws === 'tie') robotLog.value.push('Ничья — раунд не засчитан в победы.')
      else if (ws === 'player') robotLog.value.push('Вы выиграли раунд.')
      else robotLog.value.push('Робот выиграл раунд.')
    }
  }
}

async function pollRobotState() {
  if (!robotSession.value || !auth.token) return
  try {
    const resp = await fetch(
      `/api/rps/robot/state?session_id=${encodeURIComponent(robotSession.value)}`,
      { headers: { Authorization: `Bearer ${auth.token}` } }
    )
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) return
    applyRobotState(data)
  } catch {}
}

function startRobotPoll() {
  stopRobotPoll()
  robotPollTimer = window.setInterval(() => void pollRobotState(), 300)
}

async function startRobotMatch() {
  playSfx('button')
  robotError.value = ''
  robotBusy.value = true
  try {
    const resp = await fetch('/api/rps/robot/start', {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      const d = (data as any).detail
      robotError.value = typeof d === 'string' ? d : 'Не удалось начать партию.'
      return
    }
    robotSession.value = String(data.session_id ?? '')
    robotLog.value = ['Игра до 3 побед. Удачи!']
    applyRobotState(data)
    startRobotPoll()
  } catch {
    robotError.value = 'Сеть'
  } finally {
    robotBusy.value = false
  }
}

async function onRobotPick(move: RpsMove) {
  if (!robotSession.value || robotFinished.value || robotPhase.value !== 'picking') return
  playSfx('button')
  robotError.value = ''
  robotSelected.value = move
  robotBusy.value = true
  try {
    const resp = await fetch('/api/rps/robot/pick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ session_id: robotSession.value, move }),
    })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      const d = (data as any).detail
      robotError.value = typeof d === 'string' ? d : 'Выбор не принят.'
      return
    }
    applyRobotState(data)
  } catch {
    robotError.value = 'Сеть'
  } finally {
    robotBusy.value = false
  }
}

async function claimRobot() {
  if (!robotSession.value) return
  try {
    const resp = await fetch('/api/rps/robot/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ session_id: robotSession.value }),
    })
    const data = await resp.json().catch(() => ({}))
    if (resp.status === 429) {
      const w = Number((data as any)?.detail?.wait_seconds ?? 1)
      window.setTimeout(() => void claimRobot(), Math.ceil(w * 1000) + 300)
      return
    }
    if (resp.ok && (data as any).granted) {
      robotLog.value.push('Алмаз начислен.')
      await auth.refreshProfile()
    }
  } catch {}
}

function enterOnlineRoom(id: number) {
  const r = rooms.value.find((x) => x.room_id === id)
  if (r && r.occupancy >= 2) {
    playSfx('button')
    onlineError.value = 'Комната занята (2 игрока).'
    return
  }
  playSfx('button')
  onlineError.value = ''
  if (roomsTimer) {
    window.clearInterval(roomsTimer)
    roomsTimer = null
  }
  onlineRoomId.value = id
  onlineEndHandled = false
  showOnlineEndModal.value = false
  mode.value = 'online_room'
  connectWs(id)
}

function connectWs(roomId: number) {
  disconnectWs()
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/rps?token=${encodeURIComponent(auth.token)}&room=${roomId}`)
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'room.state') {
        onlineError.value = ''
        roomState.value = msg.payload
        if (msg.payload?.last_round?.match_over) {
          handleOnlineMatchEnd()
        }
        if (msg.payload?.last_round?.match_over || msg.payload?.last_round?.kind === 'forfeit') {
          if (onlineDiamondRefreshTimer) window.clearTimeout(onlineDiamondRefreshTimer)
          onlineDiamondRefreshTimer = window.setTimeout(() => {
            onlineDiamondRefreshTimer = null
            void auth.refreshProfile()
          }, 500)
        }
      }
      if (msg.type === 'room.chat' && msg.payload?.messages) {
        if (roomState.value) roomState.value = { ...roomState.value, chat: msg.payload.messages }
      }
      if (msg.type === 'room.error') onlineError.value = String(msg.message ?? 'Ошибка')
    } catch {}
  }
  ws.onclose = () => {
    ws = null
  }
  ws.onerror = () => {
    onlineError.value = 'Ошибка соединения'
  }
}

function disconnectWs() {
  if (ws) {
    try {
      ws.close()
    } catch {}
    ws = null
  }
  roomState.value = null
}

function sendWs(obj: object) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj))
}

function sendChat() {
  const t = chatDraft.value.trim()
  if (!t) return
  playSfx('button')
  sendWs({ type: 'chat', text: t })
  chatDraft.value = ''
}

function sendBetReady() {
  playSfx('button')
  onlineError.value = ''
  sendWs({ type: 'bet_ready', bet: betAmount.value, ready: true })
}

function sendPick(choice: RpsMove) {
  if (onlineBoardDisabled.value) return
  playSfx('button')
  sendWs({ type: 'pick', choice })
}

function launchDiamondFlyFromCenter() {
  void nextTick(() => {
    const hud = diamondHudRef.value
    if (!hud) return
    const hr = hud.getBoundingClientRect()
    const x1 = hr.left + hr.width / 2
    const y1 = hr.top + hr.height / 2
    const x0 = window.innerWidth / 2
    const y0 = window.innerHeight / 2 - 40
    const id = `rps_df_${Date.now()}`
    diamondFlights.value = [...diamondFlights.value, { id, x0, y0, x1, y1 }]
    window.setTimeout(() => {
      diamondFlights.value = diamondFlights.value.filter((d) => d.id !== id)
      hud.classList.add('rps-diamonds--pulse')
      window.setTimeout(() => hud.classList.remove('rps-diamonds--pulse'), 520)
      void auth.refreshProfile()
    }, 950)
    playSfx('diamond')
  })
}

function handleOnlineMatchEnd() {
  if (!roomState.value?.last_round?.match_over || onlineEndHandled) return
  onlineEndHandled = true
  showOnlineEndModal.value = true
  if (onlineMatchWon.value) {
    window.setTimeout(() => launchDiamondFlyFromCenter(), 500)
  }
}

function robotRestart() {
  showRobotEndModal.value = false
  resetRobotUi()
  void startRobotMatch()
}

function robotExitGame() {
  showRobotEndModal.value = false
  resetRobotUi()
}

function onlineRestart() {
  showOnlineEndModal.value = false
  onlineEndHandled = false
}

function onlineExitGame() {
  showOnlineEndModal.value = false
  onlineEndHandled = false
  disconnectWs()
  mode.value = 'online_lobby'
  void loadRooms()
  roomsTimer = window.setInterval(() => void loadRooms(), 2000)
}

onMounted(() => {
  startPresencePing(auth.token, GAME_KEY)
})

onBeforeUnmount(() => {
  stopPresencePing()
  stopRobotPoll()
  if (roomsTimer) window.clearInterval(roomsTimer)
  if (onlineDiamondRefreshTimer) window.clearTimeout(onlineDiamondRefreshTimer)
  disconnectWs()
})

watch(
  () => mode.value,
  (m) => {
    if (m !== 'robot') stopRobotPoll()
  }
)
</script>

<template>
  <main class="page page-menu rps-page">
    <section class="panel rps-shell">
      <header class="rps-head">
        <h1 class="rps-title">Камень · Ножницы · Бумага</h1>
        <div class="rps-head-actions">
          <span ref="diamondHudRef" class="rps-diamonds">💎 Алмазы: {{ diamonds }}</span>
          <button type="button" class="btn rps-btn-ghost" @click="goMenu" v-if="mode !== 'menu'">В меню режимов</button>
          <button type="button" class="btn" @click="exitHub">В хаб</button>
        </div>
      </header>

      <div v-if="mode === 'menu'" class="rps-menu">
        <p class="rps-hint">Классические правила. Выберите режим.</p>
        <div class="rps-menu-grid">
          <button type="button" class="btn rps-big" @click="openRobot">Игра с роботом</button>
          <p class="rps-card-note">До 3 побед. Победитель получает 1 алмаз.</p>
          <button type="button" class="btn rps-big" @click="openOnlineLobby">Онлайн — комнаты</button>
          <p class="rps-card-note">5 комнат, ставки 1–5 алмазов, до 5 побед. Победитель забирает обе ставки.</p>
        </div>
      </div>

      <div v-else-if="mode === 'robot'" class="rps-robot">
        <p v-if="robotError" class="rps-err">{{ robotError }}</p>
        <div v-if="robotSession && !showRobotEndModal" class="rps-play-layout">
          <aside class="rps-hud-sidebar" aria-label="Счёт и таймер">
            <div class="rps-hud-stat rps-hud-stat--opp">
              <span class="rps-hud-stat-label">Робот</span>
              <span class="rps-hud-stat-value" :key="'rw-' + robotWins">{{ robotWins }}</span>
              <span class="rps-hud-stat-hint">побед</span>
            </div>
            <div
              v-if="!robotFinished"
              class="rps-hud-timer"
              :class="{
                'rps-hud-timer--urgent': robotTimerUrgent,
                'rps-hud-timer--reveal': robotPhase === 'revealing',
              }"
            >
              <span class="rps-hud-timer-label">{{ robotTimerLabel }}</span>
              <div class="rps-hud-timer-ring" aria-hidden="true">
                <svg viewBox="0 0 120 120" class="rps-hud-timer-svg">
                  <circle class="rps-hud-timer-track" cx="60" cy="60" r="52" />
                  <circle
                    class="rps-hud-timer-progress"
                    cx="60"
                    cy="60"
                    r="52"
                    :style="{ strokeDashoffset: `${326.73 * (1 - robotTimerProgress / 100)}` }"
                  />
                </svg>
                <span class="rps-hud-timer-num" :key="`rt-${robotPhase}-${robotTimerSec}`">{{ robotTimerSec }}</span>
              </div>
              <span class="rps-hud-timer-unit">сек</span>
            </div>
            <div class="rps-hud-stat rps-hud-stat--you">
              <span class="rps-hud-stat-label">Вы</span>
              <span class="rps-hud-stat-value" :key="'pw-' + playerWins">{{ playerWins }}</span>
              <span class="rps-hud-stat-hint">побед</span>
            </div>
          </aside>
          <div class="rps-play-main">
            <RpsCardBoard
              :selected="robotSelected"
              :opponent-revealed="robotBoardRevealed"
              :opponent-moves="robotOppMoves"
              :disabled="robotBoardDisabled"
              :highlight-winner="robotHighlight"
              :round-verdict="robotRoundVerdict"
              @pick="onRobotPick"
            />
          </div>
        </div>
        <div v-else class="rps-robot-actions">
          <button type="button" class="btn" :disabled="robotBusy" @click="startRobotMatch">Начать партию</button>
        </div>
        <ul v-if="robotLog.length" class="rps-log">
          <li v-for="(line, i) in robotLog" :key="i">{{ line }}</li>
        </ul>
      </div>

      <div v-else-if="mode === 'online_lobby'" class="rps-lobby">
        <p v-if="onlineError" class="rps-err">{{ onlineError }}</p>
        <p class="rps-hint">Занято = 2 игрока подключены по сети. Войти нельзя.</p>
        <div class="rps-room-grid">
          <button
            v-for="r in rooms"
            :key="r.room_id"
            type="button"
            class="btn rps-room-btn"
            :disabled="r.occupancy >= 2"
            @click="enterOnlineRoom(r.room_id)"
          >
            Комната {{ r.room_id + 1 }}
            <span class="rps-room-meta">{{ r.occupancy }} / 2</span>
          </button>
        </div>
      </div>

      <div v-else-if="mode === 'online_room' && roomState" class="rps-online">
        <p v-if="onlineError" class="rps-err">{{ onlineError }}</p>
        <h2 class="rps-sub">Комната {{ onlineRoomId + 1 }} · {{ roomState.phase === 'waiting' ? 'ожидание' : roomState.phase === 'betting' ? 'ставки' : 'матч' }}</h2>
        <p class="rps-hint">Игроки: {{ (roomState.players || []).join(', ') || '—' }}</p>

        <div v-if="roomState.phase === 'betting'" class="rps-bet-block">
          <label class="rps-bet-label">Ставка (1–5)</label>
          <input v-model.number="betAmount" class="admin-input rps-bet-input" type="number" min="1" max="5" />
          <button type="button" class="btn" @click="sendBetReady">Готов</button>
        </div>

        <div v-if="roomState.phase === 'playing'" class="rps-match">
          <div class="rps-pot">Банк: {{ roomState.pot }} · {{ stakeLine }}</div>
          <div v-if="!showOnlineEndModal" class="rps-play-layout">
            <aside class="rps-hud-sidebar" aria-label="Счёт и таймер">
              <div class="rps-hud-stat rps-hud-stat--opp">
                <span class="rps-hud-stat-label">{{ onlineOpponentLabel }}</span>
                <span class="rps-hud-stat-value" :key="'oow-' + onlineEndScores.opponent">{{ onlineEndScores.opponent }}</span>
                <span class="rps-hud-stat-hint">побед</span>
              </div>
              <div
                class="rps-hud-timer"
                :class="{
                  'rps-hud-timer--urgent': onlineTimerUrgent,
                  'rps-hud-timer--reveal': onlineRoundPhase === 'reveal',
                }"
              >
                <span class="rps-hud-timer-label">{{ onlineTimerLabel }}</span>
                <div class="rps-hud-timer-ring" aria-hidden="true">
                  <svg viewBox="0 0 120 120" class="rps-hud-timer-svg">
                    <circle class="rps-hud-timer-track" cx="60" cy="60" r="52" />
                    <circle
                      class="rps-hud-timer-progress"
                      cx="60"
                      cy="60"
                      r="52"
                      :style="{ strokeDashoffset: `${326.73 * (1 - onlineTimerProgress / 100)}` }"
                    />
                  </svg>
                  <span class="rps-hud-timer-num" :key="`ot-${onlineRoundPhase}-${onlineTimerSec}`">{{ onlineTimerSec }}</span>
                </div>
                <span class="rps-hud-timer-unit">сек</span>
              </div>
              <div class="rps-hud-stat rps-hud-stat--you">
                <span class="rps-hud-stat-label">Вы</span>
                <span class="rps-hud-stat-value" :key="'opw-' + onlineEndScores.player">{{ onlineEndScores.player }}</span>
                <span class="rps-hud-stat-hint">побед</span>
              </div>
            </aside>
            <div class="rps-play-main">
              <RpsCardBoard
                :selected="onlineSelected"
                :opponent-revealed="onlineBoardRevealed"
                :opponent-moves="onlineOppMoves"
                :disabled="onlineBoardDisabled"
                :highlight-winner="onlineHighlight"
                :round-verdict="onlineRoundVerdict"
                @pick="sendPick"
              />
            </div>
          </div>
        </div>

        <div class="rps-chat">
          <h3 class="rps-chat-title">Чат</h3>
          <div class="rps-chat-log">
            <div v-for="(m, idx) in roomState.chat || []" :key="idx" class="rps-chat-line">
              <b>{{ m.from }}:</b> {{ m.text }}
            </div>
          </div>
          <div class="rps-chat-row">
            <input v-model="chatDraft" class="admin-input rps-chat-input" maxlength="400" placeholder="Сообщение…" @keydown.enter.prevent="sendChat" />
            <button type="button" class="btn" @click="sendChat">Отправить</button>
          </div>
        </div>
      </div>

      <div v-else-if="mode === 'online_room'" class="rps-online">
        <p class="rps-hint">Подключение…</p>
      </div>
    </section>

    <RpsMatchEndModal
      :show="showRobotEndModal"
      :won="robotWonMatch"
      :player-score="playerWins"
      :opponent-score="robotWins"
      opponent-label="робот"
      :reward-pending="robotRewardPending"
      @restart="robotRestart"
      @exit="robotExitGame"
    />
    <RpsMatchEndModal
      :show="showOnlineEndModal"
      :won="onlineMatchWon"
      :player-score="onlineEndScores.player"
      :opponent-score="onlineEndScores.opponent"
      :opponent-label="onlineOpponentLabel"
      @restart="onlineRestart"
      @exit="onlineExitGame"
    />

    <Teleport to="body">
      <div
        v-for="d in diamondFlights"
        :key="d.id"
        class="rps-diamond-fly"
        :style="{
          '--x0': `${d.x0}px`,
          '--y0': `${d.y0}px`,
          '--x1': `${d.x1}px`,
          '--y1': `${d.y1}px`,
        }"
        aria-hidden="true"
      >
        💎
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.rps-page {
  min-height: 100vh;
}
.rps-shell {
  max-width: min(920px, 100%);
  margin: 0 auto;
  padding: 18px 16px 32px;
}
.rps-diamond-fly {
  position: fixed;
  left: var(--x0);
  top: var(--y0);
  z-index: 250;
  font-size: 2rem;
  pointer-events: none;
  filter: drop-shadow(0 4px 12px rgba(100, 200, 255, 0.8));
  animation: rpsDiamondFly 0.92s cubic-bezier(0.25, 0.85, 0.35, 1) forwards;
}
@keyframes rpsDiamondFly {
  0% {
    transform: translate(-50%, -50%) scale(1.2) rotate(-12deg);
    opacity: 1;
  }
  70% {
    opacity: 1;
  }
  100% {
    left: var(--x1);
    top: var(--y1);
    transform: translate(-50%, -50%) scale(0.45) rotate(18deg);
    opacity: 0.15;
  }
}
.rps-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}
.rps-title {
  margin: 0;
  font-size: 1.45rem;
}
.rps-head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.rps-diamonds {
  font-size: 14px;
  opacity: 0.9;
  transition: transform 0.35s ease;
}
.rps-diamonds--pulse {
  animation: rpsHudPulse 0.5s ease;
}
@keyframes rpsHudPulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.12);
  }
}
.rps-btn-ghost {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.14);
}
.rps-hint {
  opacity: 0.82;
  font-size: 14px;
  margin: 0 0 14px;
}
.rps-menu {
  margin: 0 -16px;
  padding: 28px 20px 36px;
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(8, 12, 22, 0.72) 0%, rgba(8, 12, 22, 0.88) 100%),
    url('/games/rps/rps_background.jpg') center / cover no-repeat;
}
.rps-menu .rps-hint,
.rps-menu .rps-card-note {
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.85);
}
.rps-menu-grid {
  display: grid;
  gap: 12px;
}
.rps-big {
  width: 100%;
  min-height: 48px;
  font-size: 16px;
}
.rps-card-note {
  margin: -4px 0 8px;
  font-size: 13px;
  opacity: 0.78;
}
.rps-err {
  color: #ff9a9a;
  margin: 0 0 10px;
  font-size: 14px;
}
.rps-play-layout {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  margin: 8px 0 16px;
}
.rps-play-main {
  flex: 1;
  min-width: 0;
}
.rps-hud-sidebar {
  flex: 0 0 auto;
  width: min(168px, 28vw);
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 12px;
}
.rps-hud-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 12px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(165deg, rgba(28, 42, 78, 0.92), rgba(14, 20, 38, 0.95));
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease,
    border-color 0.25s ease;
}
.rps-hud-stat:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
}
.rps-hud-stat--you {
  border-color: rgba(144, 202, 249, 0.45);
}
.rps-hud-stat--you:hover {
  border-color: rgba(144, 202, 249, 0.7);
}
.rps-hud-stat--opp {
  border-color: rgba(255, 138, 128, 0.35);
}
.rps-hud-stat--opp:hover {
  border-color: rgba(255, 138, 128, 0.55);
}
.rps-hud-stat-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  opacity: 0.8;
  margin-bottom: 4px;
}
.rps-hud-stat-value {
  font-size: clamp(2.4rem, 6vw, 3rem);
  font-weight: 900;
  line-height: 1;
  animation: rpsHudScorePop 0.45s cubic-bezier(0.34, 1.45, 0.64, 1);
}
.rps-hud-stat--you .rps-hud-stat-value {
  color: #90caf9;
  text-shadow: 0 0 24px rgba(144, 202, 249, 0.45);
}
.rps-hud-stat--opp .rps-hud-stat-value {
  color: #ffab91;
  text-shadow: 0 0 20px rgba(255, 138, 128, 0.35);
}
.rps-hud-stat-hint {
  margin-top: 4px;
  font-size: 0.7rem;
  opacity: 0.55;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.rps-hud-timer {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14px 10px 12px;
  border-radius: 18px;
  border: 1px solid rgba(255, 204, 128, 0.35);
  background: linear-gradient(165deg, rgba(48, 38, 18, 0.9), rgba(24, 18, 8, 0.95));
  box-shadow: 0 8px 28px rgba(255, 167, 38, 0.15);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}
.rps-hud-timer:hover {
  transform: scale(1.03);
}
.rps-hud-timer--urgent {
  border-color: rgba(255, 82, 82, 0.65);
  box-shadow: 0 0 28px rgba(255, 82, 82, 0.35);
  animation: rpsHudTimerPulse 0.85s ease-in-out infinite;
}
.rps-hud-timer--reveal .rps-hud-timer-progress {
  stroke: #81c784;
}
.rps-hud-timer--reveal {
  border-color: rgba(129, 199, 132, 0.45);
}
.rps-hud-timer-label {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #ffcc80;
  margin-bottom: 8px;
}
.rps-hud-timer-ring {
  position: relative;
  width: 120px;
  height: 120px;
}
.rps-hud-timer-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.rps-hud-timer-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.1);
  stroke-width: 8;
}
.rps-hud-timer-progress {
  fill: none;
  stroke: #ffb74d;
  stroke-width: 8;
  stroke-linecap: round;
  stroke-dasharray: 326.73;
  transition: stroke-dashoffset 0.35s linear;
}
.rps-hud-timer-num {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.5rem;
  font-weight: 900;
  color: #fff;
  animation: rpsHudTick 0.35s ease;
}
.rps-hud-timer-unit {
  margin-top: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  opacity: 0.65;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
@keyframes rpsHudScorePop {
  from {
    transform: scale(0.6);
    opacity: 0.4;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
@keyframes rpsHudTick {
  0% {
    transform: scale(1.25);
    opacity: 0.5;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}
@keyframes rpsHudTimerPulse {
  0%,
  100% {
    box-shadow: 0 0 16px rgba(255, 82, 82, 0.25);
  }
  50% {
    box-shadow: 0 0 32px rgba(255, 82, 82, 0.55);
  }
}
@media (max-width: 720px) {
  .rps-play-layout {
    flex-direction: column;
  }
  .rps-hud-sidebar {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: center;
    position: static;
  }
  .rps-hud-stat {
    flex: 1 1 100px;
    min-width: 100px;
  }
  .rps-hud-timer {
    flex: 1 1 140px;
    min-width: 140px;
  }
}
.rps-robot-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.rps-moves {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}
.rps-reveal {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(120, 160, 255, 0.12);
  border: 1px solid rgba(140, 170, 255, 0.25);
  margin-bottom: 10px;
}
.rps-vs {
  opacity: 0.7;
  font-size: 13px;
}
.rps-log {
  margin: 14px 0 0;
  padding-left: 18px;
  font-size: 13px;
  opacity: 0.88;
  line-height: 1.45;
}
.rps-lobby .rps-room-grid {
  display: grid;
  gap: 10px;
}
.rps-room-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.rps-room-meta {
  opacity: 0.75;
  font-size: 13px;
}
.rps-sub {
  margin: 0 0 8px;
  font-size: 1.1rem;
}
.rps-bet-block {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}
.rps-bet-label {
  font-size: 13px;
}
.rps-bet-input {
  width: 80px;
}
.rps-pot {
  font-size: 14px;
  margin-bottom: 8px;
}
.rps-last {
  font-size: 13px;
  opacity: 0.9;
  margin: 0 0 8px;
}
.rps-timer {
  font-size: 1.05rem;
  font-weight: 700;
  margin: 8px 0;
  color: #ffcc80;
}
.rps-round-banner {
  margin: 0 0 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(120, 160, 255, 0.12);
  border: 1px solid rgba(140, 170, 255, 0.25);
  font-size: 0.95rem;
}
.rps-chat {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}
.rps-chat-title {
  margin: 0 0 8px;
  font-size: 1rem;
}
.rps-chat-log {
  max-height: 200px;
  overflow: auto;
  font-size: 13px;
  margin-bottom: 8px;
}
.rps-chat-line {
  margin-bottom: 4px;
}
.rps-chat-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.rps-chat-input {
  flex: 1 1 200px;
  min-width: 160px;
}
</style>
