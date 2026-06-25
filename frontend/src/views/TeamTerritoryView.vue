<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { i18n } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { playSfx } from '../audio/sound'
import { startPresencePing, stopPresencePing } from '../telemetry/presence'
import { TEAM_TERRITORY_COMING_SOON } from '../config/features'

const GAME_KEY = 'team_territory'
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t, locale } = useI18n()

const roomId = ref('default')
const error = ref<string | null>(null)
const payload = ref<any>(null)
const wsConnected = ref(false)
const wsEverGotState = ref(false)
const wsRef = ref<WebSocket | null>(null)
const tickNow = ref(Date.now())
const mathAnswer = ref('')
const spellAnswer = ref('')
const lastRoundResult = ref<{ success: boolean; paint_awarded: number; session_done?: boolean } | null>(null)
const toastMsg = ref('')
const toastErr = ref(false)
const paintBurst = ref(false)
let toastTimer: number | null = null
let paintBurstTimer: number | null = null
const reconnectAttempt = ref(0)
let reconnectTimer: number | null = null
const reducedMotion = ref(
  typeof window !== 'undefined' && window.matchMedia?.('prefers-reduced-motion: reduce)')?.matches
)

let tickTimer: number | null = null
let intentionalWsClose = false

const showGuide = ref(false)
const repaintConfirm = ref<{ cell: number; teamId: number } | null>(null)
const hoverCell = ref<number | null>(null)
const boardAreaRef = ref<HTMLElement | null>(null)
const cellPx = ref(28)
const isMobileLayout = ref(false)
const tickCountdownAnchor = ref<{ receivedAt: number; closesInMs: number; tickMs: number } | null>(null)

const SIDEBAR_W = 462
const GRID_GAP = 3
const GRID_WRAP_PAD = 20

let boardResizeObs: ResizeObserver | null = null

const guideSections = computed(() => {
  const loc = i18n.global.locale.value
  const msg = i18n.global.getLocaleMessage(loc) as Record<string, unknown>
  const tt = msg?.teamTerritory as Record<string, unknown> | undefined
  const raw = tt?.guideSections
  return Array.isArray(raw) ? (raw as Array<{ title?: string; html?: string }>) : []
})

function openGuide() {
  playSfx('button')
  showGuide.value = true
}

function closeGuide() {
  showGuide.value = false
}

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

const selectedCell = computed(() => {
  const c = me.value?.claim_cell
  return typeof c === 'number' ? c : null
})

const teamScores = computed(() => {
  const counts: Record<number, number> = {}
  for (const c of cells.value) {
    const tid = Number(c)
    if (tid >= 0) counts[tid] = (counts[tid] ?? 0) + 1
  }
  const comboMap = payload.value?.combo_counts ?? {}
  return teams.value.map((tm: any) => ({
    id: Number(tm.id),
    name: String(tm.name ?? `Team ${Number(tm.id) + 1}`),
    hex: String(tm.hex ?? '#666'),
    score: counts[Number(tm.id)] ?? 0,
    combos: Number(comboMap[String(tm.id)] ?? comboMap[Number(tm.id)] ?? 0),
  }))
})

const teamScoresRanked = computed(() =>
  [...teamScores.value].sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score
    if (b.combos !== a.combos) return b.combos - a.combos
    return a.id - b.id
  }),
)

const comboCenterCellSet = computed(() => {
  const raw = payload.value?.combo_center_cells
  if (!Array.isArray(raw)) return new Set<number>()
  return new Set(raw.map((x: unknown) => Number(x)))
})

const comboCellSet = computed(() => {
  const raw = payload.value?.combo_cells
  if (!Array.isArray(raw)) return new Set<number>()
  return new Set(raw.map((x: unknown) => Number(x)))
})

const tickClaims = computed((): Record<number, number[]> => {
  const raw = payload.value?.tick_claims ?? {}
  const out: Record<number, number[]> = {}
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    const cell = Number(k)
    if (!Number.isFinite(cell)) continue
    const ids = Array.isArray(v) ? [...new Set(v.map((x) => Number(x)).filter((n) => n >= 0))].sort() : []
    if (ids.length) out[cell] = ids
  }
  return out
})

const opponentInkRows = computed(() => {
  const by = payload.value?.opponent_ink?.by_team ?? {}
  return Object.entries(by).map(([tid, sum]) => {
    const tm = teams.value.find((x: any) => String(x.id) === String(tid))
    return {
      id: Number(tid),
      name: tm?.name ? String(tm.name) : `Team ${Number(tid) + 1}`,
      sum: Number(sum ?? 0),
    }
  })
})

function challengeModeLabel(mode: number): string {
  if (mode === 1) return t('teamTerritory.challenge.modeMath')
  if (mode === 2) return t('teamTerritory.challenge.modeSpell')
  if (mode === 3) return t('teamTerritory.challenge.modeSequence')
  return String(mode)
}

function finishReasonLabel(reason: string | undefined): string {
  const k = String(reason ?? '')
  const key = `teamTerritory.finish.reason.${k}`
  const v = t(key)
  return v !== key ? v : k
}

const scoreRows = computed(() => {
  const sc = payload.value?.scores ?? {}
  const comboBonus = payload.value?.combo_bonus ?? {}
  const balanceBonus = payload.value?.balance_bonus ?? {}
  const finalSc = payload.value?.final_scores ?? {}
  const comboCounts = payload.value?.combo_counts ?? {}
  const finished = phase.value === 'finished'
  return teams.value.map((tm: any) => {
    const id = Number(tm.id)
    const territory = Number(sc[String(id)] ?? sc[id] ?? 0)
    const combos = Number(comboCounts[String(id)] ?? comboCounts[id] ?? 0)
    const combo = Number(comboBonus[String(id)] ?? comboBonus[id] ?? 0)
    const balance = Number(balanceBonus[String(id)] ?? balanceBonus[id] ?? 0)
    const total = finished
      ? Number(finalSc[String(id)] ?? finalSc[id] ?? territory + combo + balance)
      : territory
    return {
      id,
      name: String(tm.name ?? ''),
      hex: String(tm.hex ?? '#666'),
      territory,
      combos,
      comboBonus: combo,
      balanceBonus: balance,
      score: total,
    }
  })
})

const opponentInkSum = computed(() => Number(payload.value?.opponent_ink?.sum ?? 0))

const tickProgress = computed(() => {
  void tickNow.value
  const left = msToNextTick.value
  const anchor = tickCountdownAnchor.value
  if (left == null || !anchor) return 100
  const tickMs = Math.max(1, anchor.tickMs)
  return Math.min(100, Math.max(0, ((tickMs - left) / tickMs) * 100))
})

function syncTickCountdownAnchor(snap: Record<string, unknown>) {
  const phase = String(snap?.phase ?? '')
  const closesIn = snap?.tick_closes_in_ms
  const tickMs = Number((snap?.config as Record<string, unknown>)?.tick_ms ?? 6000)
  if (phase !== 'playing' || typeof closesIn !== 'number' || !Number.isFinite(closesIn)) {
    tickCountdownAnchor.value = null
    return
  }
  tickCountdownAnchor.value = {
    receivedAt: Date.now(),
    closesInMs: Math.max(0, closesIn),
    tickMs: Math.max(1, tickMs),
  }
}

const paintFillPct = computed(() => {
  const cur = Number(me.value?.paint ?? 0)
  const max = Number(cfg.value?.paint_max ?? 10)
  return max > 0 ? Math.min(100, (cur / max) * 100) : 0
})

const repaintCost = computed(() => Math.max(1, Number(cfg.value?.repaint_cost ?? 2)))

const inviteCooldownMs = computed(() => {
  void tickNow.value
  const iso = payload.value?.invite_cooldown_until
  if (!iso) return null
  const ts = Date.parse(String(iso))
  if (!Number.isFinite(ts)) return null
  return Math.max(0, ts - Date.now())
})

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${g.value}, ${cellPx.value}px)`,
  gap: `${GRID_GAP}px`,
}))

function detectMobileLayout() {
  isMobileLayout.value = window.matchMedia('(max-width: 900px), (pointer: coarse)').matches
}

function recomputeCellSize() {
  detectMobileLayout()
  const gSize = g.value
  if (isMobileLayout.value) {
    cellPx.value = gSize > 12 ? 22 : 28
    return
  }
  const area = boardAreaRef.value
  let availW: number
  let availH: number
  if (area && area.clientWidth > 0 && area.clientHeight > 0) {
    availW = area.clientWidth - GRID_WRAP_PAD
    availH = area.clientHeight - GRID_WRAP_PAD
  } else {
    const rootPad = 32
    const headerH = 56
    const gap = 14
    availW = window.innerWidth - rootPad - SIDEBAR_W - gap - GRID_WRAP_PAD
    availH = window.innerHeight - headerH - rootPad - GRID_WRAP_PAD
  }
  if (availW < 120 || availH < 120) {
    cellPx.value = 24
    return
  }
  const fromW = (availW - GRID_GAP * (gSize - 1)) / gSize
  const fromH = (availH - GRID_GAP * (gSize - 1)) / gSize
  cellPx.value = Math.max(14, Math.floor(Math.min(fromW, fromH)))
}

function attachBoardResizeObserver() {
  boardResizeObs?.disconnect()
  boardResizeObs = null
  const area = boardAreaRef.value
  if (!area || typeof ResizeObserver === 'undefined') return
  boardResizeObs = new ResizeObserver(() => recomputeCellSize())
  boardResizeObs.observe(area)
}

let resizeTimer: number | null = null
function onWindowResize() {
  if (resizeTimer) window.clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    recomputeCellSize()
    resizeTimer = null
  }, 80)
}

watch([g, phase, cells], () => {
  nextTick(() => {
    recomputeCellSize()
    if (phase.value === 'playing' || phase.value === 'finished') {
      attachBoardResizeObserver()
    }
  })
})

const isVoidMatchFinish = computed(() => {
  const r = String(payload.value?.finish_reason ?? '')
  return r === 'stale_idle' || r === 'opponent_left' || r === 'one_sided_idle'
})

const isScoreTie = computed(() => {
  const wins = (payload.value?.winning_team_ids ?? []) as number[]
  return wins.length > 1
})

const myMatchReward = computed(() => ({
  kind: String(me.value?.match_reward_kind ?? ''),
  diamonds: Number(me.value?.match_reward_diamonds ?? 0),
}))

const challengeInGap = computed(() => {
  void tickNow.value
  const ch = challenge.value
  if (!ch?.next_round_not_before) return false
  const gap = Date.parse(String(ch.next_round_not_before))
  return Number.isFinite(gap) && Date.now() < gap
})

const challengeGapSeconds = computed(() => {
  void tickNow.value
  const ch = challenge.value
  if (!ch?.next_round_not_before) return 0
  const gap = Date.parse(String(ch.next_round_not_before))
  if (!Number.isFinite(gap)) return 0
  return Math.max(0, Math.ceil((gap - Date.now()) / 1000))
})

const showChallengeRoundResult = computed(() => !!lastRoundResult.value && challengeInGap.value)

const challengeMaxPaint = computed(() => Number(cfg.value?.challenge_max_paint_start ?? 5))

const challengeBlockedByPaint = computed(() => Number(me.value?.paint ?? 0) > challengeMaxPaint.value)

const challengeDeadline = computed(() => {
  void tickNow.value
  const ch = challenge.value
  if (!ch?.round_deadline_at || challengeInGap.value) return null
  const end = Date.parse(String(ch.round_deadline_at))
  if (!Number.isFinite(end)) return null
  const mode = Number(challenge.value?.mode)
  const totalSec =
    mode === 3
      ? Number(challenge.value?.round_seconds ?? cfg.value?.challenge_sequence_sec ?? 8)
      : mode === 1
        ? Number(challenge.value?.round_seconds ?? cfg.value?.challenge_math_sec ?? 7)
        : Number(challenge.value?.round_seconds ?? cfg.value?.challenge_riddle_sec ?? 5)
  const totalMs = Math.max(1000, totalSec * 1000)
  const leftMs = Math.max(0, end - Date.now())
  const pct = Math.min(100, Math.max(0, (leftMs / totalMs) * 100))
  return {
    seconds: Math.ceil(leftMs / 1000),
    pct,
    urgent: leftMs <= 2000,
  }
})

const msToNextRegen = computed(() => {
  void tickNow.value
  const paint = Number(me.value?.paint ?? 0)
  const max = Number(cfg.value?.paint_max ?? 10)
  if (paint >= max) return null
  const iso = me.value?.next_regen_at
  if (!iso) return null
  const ts = Date.parse(String(iso))
  if (!Number.isFinite(ts)) return null
  const left = Math.max(0, ts - Date.now())
  return { ms: left, seconds: Math.ceil(left / 1000) }
})

function ttErrorMessage(code: string): string {
  const k = String(code ?? '').trim()
  const key = `teamTerritory.toasts.${k}`
  const v = t(key)
  return v !== key ? v : k || t('errors.generic')
}

function showToast(message: string, err = false) {
  toastMsg.value = message
  toastErr.value = err
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toastMsg.value = ''
    toastTimer = null
  }, 3200)
}

function triggerPaintBurst() {
  paintBurst.value = true
  if (paintBurstTimer) window.clearTimeout(paintBurstTimer)
  paintBurstTimer = window.setTimeout(() => {
    paintBurst.value = false
    paintBurstTimer = null
  }, 900)
}

type LobbyPlayer = { username: string; team_id: number; ready: boolean }

const lobbyRoster = computed((): LobbyPlayer[] => {
  const out: LobbyPlayer[] = []
  const pmap = payload.value?.players ?? {}
  for (const [username, slot] of Object.entries(pmap) as [string, any][]) {
    if (slot?.role !== 'player') continue
    out.push({
      username,
      team_id: Number(slot.team_id ?? 0),
      ready: !!slot.ready,
    })
  }
  return out
})

const lobbyDisconnected = computed(
  () => phase.value === 'lobby' && !wsEverGotState.value && !error.value,
)
const myTeamId = computed(() => Number(me.value?.team_id ?? 0))
const iAmReady = computed(() => !!me.value?.ready)

function teamLabel(tm: { key?: string; name?: string }): string {
  const k = String(tm?.key ?? '')
  if (k) {
    const key = `teamTerritory.teams.${k}`
    const v = t(key)
    if (v !== key) return v
  }
  return String(tm?.name ?? '')
}

const teamsWithPlayers = computed(() =>
  teams.value.map((tm: any) => {
    const id = Number(tm.id)
    const members = lobbyRoster.value.filter((p) => p.team_id === id)
    return {
      id,
      key: String(tm.key ?? ''),
      hex: String(tm.hex ?? '#666'),
      name: teamLabel(tm),
      players: members,
      count: members.length,
      readyCount: members.filter((p) => p.ready).length,
    }
  }),
)

const myTeam = computed(() => teamsWithPlayers.value.find((t) => t.id === myTeamId.value))
const opponentTeams = computed(() => teamsWithPlayers.value.filter((t) => t.id !== myTeamId.value))
const opponentPlayerCount = computed(() => opponentTeams.value.reduce((sum, t) => sum + t.count, 0))

const lobbyReadyStats = computed(() => {
  const ready = lobbyRoster.value.filter((p) => p.ready)
  return {
    players: lobbyRoster.value.length,
    ready: ready.length,
    teamsReady: new Set(ready.map((p) => p.team_id)).size,
  }
})

const lobbyTeamImbalanced = computed(() => {
  const counts = teamsWithPlayers.value.map((t) => t.count)
  if (!counts.length) return false
  return Math.max(...counts) - Math.min(...counts) >= 2
})

const lobbyCanStart = computed(() => {
  if (lobbyTeamImbalanced.value) return false
  return lobbyReadyStats.value.teamsReady >= 2
})

function teamHexById(teamId: number): string {
  const tm = teams.value.find((x: any) => Number(x?.id) === teamId)
  return tm?.hex ? String(tm.hex) : '#888'
}

function claimBorderGradient(teamIds: number[]): string {
  const colors = teamIds.map((id) => teamHexById(id))
  if (colors.length === 1) {
    const c = colors[0]
    const dim = hexAlpha(c, 0.22)
    return `conic-gradient(from var(--tt-claim-angle, 0deg), ${c} 0deg 90deg, ${dim} 90deg 180deg, ${c} 180deg 270deg, ${dim} 270deg 360deg)`
  }
  const n = colors.length
  const stops = colors
    .map((hex, i) => {
      const a = (i / n) * 360
      const b = ((i + 1) / n) * 360
      return `${hex} ${a}deg ${b}deg`
    })
    .join(', ')
  return `conic-gradient(from var(--tt-claim-angle, 0deg), ${stops})`
}

function hexAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  if (h.length !== 6) return hex
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function teamStyle(teamId: number) {
  const tm = teams.value.find((x: any) => Number(x?.id) === teamId)
  const hex = tm?.hex ? String(tm.hex) : '#666'
  return { background: teamId < 0 ? 'rgba(80,90,110,0.35)' : hex }
}

function cellStyle(teamId: number, index: number) {
  const claimTeams = tickClaims.value[index]
  const claimVars: Record<string, string> = {}
  if (phase.value === 'playing' && claimTeams?.length) {
    claimVars['--tt-claim-gradient'] = claimBorderGradient(claimTeams)
  }
  const hoverPreview =
    hoverCell.value === index &&
    phase.value === 'playing' &&
    canClaimCell(teamId, index) &&
    !isSpectator.value &&
    !challenge.value &&
    myTeamId.value >= 0
  if (hoverPreview) {
    const hex = teamHexById(myTeamId.value)
    return {
      background: hexAlpha(hex, 0.38),
      ...claimVars,
    }
  }
  const base = teamStyle(teamId)
  if (teamId < 0) return { ...base, ...claimVars }
  const tm = teams.value.find((x: any) => Number(x?.id) === teamId)
  const hex = tm?.hex ? String(tm.hex) : '#888'
  if (!comboCellSet.value.has(index)) return { ...base, ...claimVars }
  return {
    ...base,
    ...claimVars,
    '--tt-neon': hex,
    '--tt-neon-bright': hexAlpha(hex, 1),
    '--tt-neon-glow': hexAlpha(hex, 0.95),
    '--tt-neon-soft': hexAlpha(hex, 0.65),
    '--tt-neon-faint': hexAlpha(hex, 0.36),
  } as Record<string, string>
}

function scheduleReconnect() {
  if (intentionalWsClose || TEAM_TERRITORY_COMING_SOON) return
  const delay = Math.min(8000, 500 + reconnectAttempt.value * 800)
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  reconnectTimer = window.setTimeout(() => {
    reconnectAttempt.value += 1
    connectWs()
  }, delay)
}

function connectWs() {
  error.value = null
  if (!auth.token) {
    error.value = t('errors.unauthorized')
    return
  }
  wsRef.value?.close()
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/ws/team-territory?token=${encodeURIComponent(auth.token)}&room_id=${encodeURIComponent(roomId.value)}`
  const ws = new WebSocket(url)
  wsRef.value = ws
  ws.onopen = () => {
    reconnectAttempt.value = 0
    wsConnected.value = true
  }
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'state' && msg.payload) {
        wsEverGotState.value = true
        const prev = payload.value?.phase
        payload.value = msg.payload
        syncTickCountdownAnchor(msg.payload)
        if (!msg.payload.challenge && lastRoundResult.value && !challengeInGap.value) {
          lastRoundResult.value = null
        }
        if (msg.payload.phase === 'finished' && prev !== 'finished') void auth.refreshProfile()
      } else if (msg.type === 'error') {
        showToast(ttErrorMessage(String(msg.message ?? '')), true)
      } else if (msg.type === 'buy_paint_result' && msg.payload) {
        if (msg.payload.ok) {
          playSfx('purchase')
          showToast(t('teamTerritory.toasts.paintBought', { amount: cfg.value?.bundle ?? 3 }))
        } else {
          showToast(ttErrorMessage(String(msg.payload.error ?? '')), true)
        }
      } else if (msg.type === 'challenge_result' && msg.payload) {
        lastRoundResult.value = {
          success: !!msg.payload.success,
          paint_awarded: Number(msg.payload.paint_awarded ?? 0),
          session_done: !!msg.payload.session_done,
        }
        if (msg.payload.success && Number(msg.payload.paint_awarded ?? 0) > 0) {
          playSfx('purchase')
          triggerPaintBurst()
        }
        if (msg.payload.session_done) {
          window.setTimeout(() => {
            lastRoundResult.value = null
          }, 2500)
        }
      }
    } catch {
      /* ignore */
    }
  }
  ws.onclose = () => {
    wsRef.value = null
    wsConnected.value = false
    scheduleReconnect()
  }
}

function send(msg: Record<string, unknown>) {
  const ws = wsRef.value
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
}

function pickTeam(teamId: number) {
  if (iAmReady.value) return
  playSfx('button')
  send({ type: 'set_team', team_id: teamId })
}

function toggleReady() {
  if (!iAmReady.value && lobbyTeamImbalanced.value) {
    showToast(t('teamTerritory.toasts.teamsImbalanced'), true)
    return
  }
  playSfx('button')
  send({ type: 'set_ready', ready: !iAmReady.value })
}

function canClaimCell(teamId: number, index: number): boolean {
  if (teamId < 0) return true
  if (comboCellSet.value.has(index)) return false
  if (teamId === myTeamId.value) return false
  return true
}

function submitClaim(idx: number) {
  playSfx('button')
  send({ type: 'claim', cell: idx })
}

function claimCell(idx: number, teamId: number) {
  if (isSpectator.value || phase.value !== 'playing' || challenge.value) return
  if (!canClaimCell(teamId, idx)) return
  if (teamId >= 0) {
    if (Number(me.value?.paint ?? 0) < repaintCost.value) {
      showToast(t('teamTerritory.toasts.notEnoughPaint', { cost: repaintCost.value }), true)
      return
    }
    repaintConfirm.value = { cell: idx, teamId }
    return
  }
  submitClaim(idx)
}

function confirmRepaint() {
  const pending = repaintConfirm.value
  if (!pending) return
  repaintConfirm.value = null
  submitClaim(pending.cell)
}

function cancelRepaint() {
  repaintConfirm.value = null
}

function buyPaint() {
  playSfx('button')
  send({ type: 'buy_paint' })
}

function startChallenge() {
  if (challengeCooldownMs.value != null && challengeCooldownMs.value > 0) return
  if (challengeBlockedByPaint.value) {
    showToast(t('teamTerritory.toasts.tooMuchPaint', { max: challengeMaxPaint.value }), true)
    return
  }
  playSfx('button')
  mathAnswer.value = ''
  spellAnswer.value = ''
  lastRoundResult.value = null
  send({ type: 'challenge_start', locale: locale.value })
}

function submitChallenge() {
  const ch = challenge.value
  if (!ch || challengeInGap.value) return
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
  if (!ch || Number(ch.mode) !== 3 || challengeInGap.value) return
  playSfx('button')
  send({ type: 'challenge_submit', label })
}

function resetLobby() {
  playSfx('button')
  send({ type: 'reset_to_lobby' })
}

function invitePlayers() {
  if (inviteCooldownMs.value != null && inviteCooldownMs.value > 0) return
  playSfx('button')
  send({ type: 'invite_players' })
  showToast(t('teamTerritory.invite.sent'))
}

const msToNextTick = computed(() => {
  void tickNow.value
  const anchor = tickCountdownAnchor.value
  if (!anchor) return null
  return Math.max(0, anchor.closesInMs - (Date.now() - anchor.receivedAt))
})

const challengeCooldownMs = computed(() => {
  void tickNow.value
  const iso = me.value?.challenge_cooldown_until
  if (!iso) return null
  const ts = Date.parse(String(iso))
  if (!Number.isFinite(ts)) return null
  return Math.max(0, ts - Date.now())
})

const msStallLeft = computed(() => {
  void tickNow.value
  const iso = stall.value?.deadline_at
  if (!iso) return null
  const ts = Date.parse(String(iso))
  if (!Number.isFinite(ts)) return null
  return Math.max(0, ts - Date.now())
})

onMounted(() => {
  if (TEAM_TERRITORY_COMING_SOON) return
  const qRoom = route.query.room
  if (typeof qRoom === 'string' && qRoom.trim()) roomId.value = qRoom.trim().slice(0, 64)
  startPresencePing(auth.token, GAME_KEY)
  connectWs()
  detectMobileLayout()
  window.addEventListener('resize', onWindowResize)
  tickTimer = window.setInterval(() => {
    tickNow.value = Date.now()
  }, 250)
  nextTick(() => {
    recomputeCellSize()
    attachBoardResizeObserver()
  })
})

onBeforeUnmount(() => {
  intentionalWsClose = true
  boardResizeObs?.disconnect()
  boardResizeObs = null
  window.removeEventListener('resize', onWindowResize)
  if (resizeTimer) window.clearTimeout(resizeTimer)
  if (toastTimer) window.clearTimeout(toastTimer)
  if (paintBurstTimer) window.clearTimeout(paintBurstTimer)
  stopPresencePing()
  if (tickTimer) window.clearInterval(tickTimer)
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  wsRef.value?.close()
})
</script>

<template>
  <div v-if="TEAM_TERRITORY_COMING_SOON" class="tt-wip">
    <header class="tt-header">
      <button type="button" class="btn tt-back" @click="router.push('/games')">← {{ t('teamTerritory.nav.hub') }}</button>
      <h1 class="tt-title">Team Territory</h1>
    </header>
    <div class="tt-wip-card card">
      <h2 class="tt-wip-title">{{ t('hub.status.inDevelopment') }}</h2>
      <p class="tt-wip-text">{{ t('teamTerritory.wip.unavailable') }}</p>
      <button type="button" class="btn btn-primary" @click="router.push('/games')">{{ t('teamTerritory.wip.backToHub') }}</button>
    </div>
  </div>
  <div v-else class="tt-root" :class="{ 'tt-root--match': phase === 'playing' || phase === 'finished' }">
    <header class="tt-header">
      <button type="button" class="btn tt-back" @click="router.push('/games')">← {{ t('teamTerritory.nav.hub') }}</button>
      <h1 class="tt-title">Team Territory</h1>
      <div class="tt-wallet">💎 {{ diamonds }}</div>
    </header>

    <div v-if="toastMsg" class="tt-toast" :class="{ 'tt-toast--err': toastErr }" role="status">{{ toastMsg }}</div>
    <div v-if="error" class="tt-err">{{ error }}</div>

    <section v-if="isSpectator" class="tt-banner">
      {{ t('teamTerritory.spectator.banner') }}
      <span v-if="me.spectator_queue_position"> {{ t('teamTerritory.spectator.queue', { pos: me.spectator_queue_position }) }}</span>
    </section>

    <section v-if="phase === 'lobby'" class="tt-lobby card">
      <div class="tt-lobby-head">
        <div>
          <h2 class="tt-lobby-title">{{ t('teamTerritory.lobby.title') }}</h2>
          <p class="tt-lobby-sub">{{ t('teamTerritory.lobby.playersCount', { n: lobbyReadyStats.players }) }}</p>
        </div>
        <div class="tt-lobby-head-actions">
          <button type="button" class="btn btn-guide-tiny" @click="openGuide">{{ t('teamTerritory.guide') }}</button>
          <div class="tt-lobby-badge" :class="{ 'tt-lobby-badge--ok': lobbyCanStart }">
            {{ t('teamTerritory.lobby.waitingAllReady', { ready: lobbyReadyStats.ready, total: lobbyReadyStats.players }) }}
          </div>
        </div>
      </div>

      <p class="tt-lobby-hint">{{ t('teamTerritory.lobby.startHint') }}</p>

      <p v-if="lobbyDisconnected" class="tt-lobby-warn">{{ t('teamTerritory.lobby.connecting') }}</p>

      <div class="tt-lobby-section">
        <h3 class="tt-lobby-section-title">{{ t('teamTerritory.lobby.pickTeam') }}</h3>
        <div class="tt-team-picker">
          <button
            v-for="tm in teamsWithPlayers"
            :key="tm.id"
            type="button"
            class="tt-team-pick"
            :class="{ 'tt-team-pick--active': myTeamId === tm.id, 'tt-team-pick--locked': iAmReady }"
            :disabled="iAmReady"
            @click="pickTeam(tm.id)"
          >
            <span class="tt-team-pick-swatch" :style="{ background: tm.hex }" />
            <span class="tt-team-pick-name">{{ tm.name }}</span>
            <span class="tt-team-pick-meta">{{ t('teamTerritory.lobby.teamPlayers', { count: tm.count }) }}</span>
          </button>
        </div>
      </div>

      <div class="tt-lobby-roster">
        <div class="tt-roster-col tt-roster-col--mine">
          <h3 class="tt-roster-title">
            <span class="tt-score-dot" :style="{ background: myTeam?.hex ?? '#666' }" />
            {{ t('teamTerritory.lobby.myTeam') }}
          </h3>
          <ul class="tt-roster-list">
            <li v-for="p in myTeam?.players ?? []" :key="p.username" class="tt-roster-item" :class="{ 'tt-roster-item--ready': p.ready }">
              <span class="tt-roster-name">
                {{ p.username }}
                <span v-if="p.username === auth.username" class="tt-you">{{ t('teamTerritory.lobby.you') }}</span>
              </span>
              <span v-if="p.ready" class="ok">{{ t('teamTerritory.lobby.readyFlag') }}</span>
            </li>
            <li v-if="!(myTeam?.players?.length)" class="tt-roster-empty muted">{{ t('teamTerritory.lobby.emptyTeam') }}</li>
          </ul>
        </div>

        <div class="tt-roster-col">
          <h3 class="tt-roster-title">
            {{ t('teamTerritory.lobby.opponents') }}
            <span class="tt-opponent-total muted">({{ opponentPlayerCount }})</span>
          </h3>
          <div v-for="ot in opponentTeams" :key="ot.id" class="tt-opponent-block">
            <div class="tt-opponent-head" :style="{ borderLeftColor: ot.hex }">
              <span class="tt-score-dot" :style="{ background: ot.hex }" />
              <span>{{ ot.name }}</span>
              <span class="muted">· {{ t('teamTerritory.lobby.teamPlayers', { count: ot.count }) }}</span>
            </div>
            <ul class="tt-roster-list tt-roster-list--compact">
              <li v-for="p in ot.players" :key="p.username" class="tt-roster-item" :class="{ 'tt-roster-item--ready': p.ready }">
                <span>{{ p.username }}</span>
                <span v-if="p.ready" class="ok">{{ t('teamTerritory.lobby.readyFlag') }}</span>
              </li>
              <li v-if="!ot.players.length" class="tt-roster-empty muted">—</li>
            </ul>
          </div>
        </div>
      </div>

      <p v-if="lobbyReadyStats.players < 2" class="tt-lobby-warn">{{ t('teamTerritory.lobby.needMinPlayers') }}</p>
      <p v-if="lobbyReadyStats.players >= 2 && lobbyReadyStats.teamsReady < 2" class="tt-lobby-warn">{{ t('teamTerritory.lobby.needTwoTeams') }}</p>
      <p v-if="lobbyTeamImbalanced" class="tt-lobby-warn">{{ t('teamTerritory.lobby.teamsImbalanced') }}</p>

      <button
        type="button"
        class="btn btn-primary tt-ready"
        :class="{ 'tt-ready--cancel': iAmReady }"
        @click="toggleReady"
      >
        {{ iAmReady ? t('teamTerritory.lobby.cancelReady') : t('teamTerritory.lobby.ready') }}
      </button>

      <button
        type="button"
        class="btn tt-invite"
        :disabled="inviteCooldownMs != null && inviteCooldownMs > 0"
        @click="invitePlayers"
      >
        <template v-if="inviteCooldownMs != null && inviteCooldownMs > 0">
          {{ t('teamTerritory.invite.cooldown', { seconds: Math.ceil(inviteCooldownMs / 1000) }) }}
        </template>
        <template v-else>{{ t('teamTerritory.invite.button') }}</template>
      </button>
    </section>

    <section
      v-if="phase === 'playing' || phase === 'finished'"
      class="tt-match"
      :class="{ 'tt-match--desktop': !isMobileLayout }"
    >
      <div ref="boardAreaRef" class="tt-board-area">
        <div
          class="tt-grid-wrap card"
          :class="{ 'tt-grid-wrap--dense': g > 12, 'tt-grid-wrap--fit': !isMobileLayout }"
        >
          <div class="tt-grid" :style="gridStyle">
            <button
              v-for="(c, i) in cells"
              :key="i"
              type="button"
              class="tt-cell"
              :class="{
                pulse: !reducedMotion && c < 0 && !tickClaims[i]?.length,
                'tt-cell--picked': selectedCell === i,
                'tt-cell--combo': comboCellSet.has(i) && c >= 0,
                'tt-cell--claimed': (tickClaims[i]?.length ?? 0) > 0,
                'tt-cell--multi-claim': (tickClaims[i]?.length ?? 0) > 1,
                'tt-cell--repaintable': canClaimCell(Number(c), i),
              }"
              :style="{ ...cellStyle(Number(c), i), width: `${cellPx}px`, height: `${cellPx}px` }"
              :disabled="isSpectator || phase !== 'playing' || !!challenge || !canClaimCell(Number(c), i)"
              @mouseenter="hoverCell = i"
              @mouseleave="hoverCell = null"
              @click="claimCell(i, Number(c))"
            >
              <span v-if="Number(c) >= 0" class="tt-cell-label">
                {{ comboCenterCellSet.has(i) ? '1+1' : '+1' }}
              </span>
            </button>
          </div>
        </div>
      </div>

      <aside class="tt-sidebar card">
        <div class="tt-stat tt-stat--tick">
          <div class="tt-stat-ring" aria-hidden="true">
            <svg viewBox="0 0 44 44">
              <circle class="tt-stat-ring-track" cx="22" cy="22" r="18" />
              <circle
                class="tt-stat-ring-fill"
                cx="22"
                cy="22"
                r="18"
                :style="{ strokeDashoffset: `${113 * (1 - tickProgress / 100)}` }"
              />
            </svg>
            <span class="tt-stat-ring-num">{{ payload?.tick_index ?? 0 }}</span>
          </div>
          <div class="tt-stat-body">
            <span class="tt-stat-label">{{ t('teamTerritory.match.tickShort') }}</span>
            <span v-if="msToNextTick != null" class="tt-stat-value" :title="t('teamTerritory.match.tickCloseIn', { seconds: Math.ceil(msToNextTick / 1000) })">
              {{ Math.ceil(msToNextTick / 1000) }}s
            </span>
          </div>
        </div>

        <div class="tt-stat">
          <div class="tt-paint-meter" :class="{ 'tt-paint-meter--burst': paintBurst }">
            <div class="tt-paint-meter-fill" :style="{ width: `${paintFillPct}%` }" />
            <span class="tt-paint-meter-text">{{ me.paint ?? 0 }}/{{ cfg.paint_max ?? 10 }}</span>
            <span v-if="paintBurst" class="tt-paint-plus">+1</span>
          </div>
          <div v-if="msToNextRegen" class="tt-stat-sub">
            <span class="tt-regen-dot" />
            {{ msToNextRegen.seconds }}s
          </div>
        </div>

        <div class="tt-stat tt-stat--ink">
          <span class="tt-stat-icon" aria-hidden="true">🎨</span>
          <div class="tt-stat-body">
            <span class="tt-stat-value">{{ opponentInkSum }}</span>
            <span class="tt-stat-label">{{ t('teamTerritory.match.opponentInkShort') }}</span>
          </div>
        </div>

        <div v-if="stall.phase === 'warn' && msStallLeft != null" class="tt-stall-banner">
          <span class="tt-stall-icon">⏳</span>
          <span>{{ Math.ceil(msStallLeft / 1000) }}s</span>
        </div>

        <TransitionGroup name="tt-team-rank" tag="div" class="tt-teams-board">
          <div
            v-for="ts in teamScoresRanked"
            :key="ts.id"
            class="tt-team-row"
            :class="{ 'tt-team-row--mine': ts.id === myTeamId }"
            :style="{ '--team-color': ts.hex }"
          >
            <span class="tt-team-swatch" :style="{ background: ts.hex }" />
            <span class="tt-team-name">{{ ts.name }}</span>
            <span class="tt-team-score">{{ ts.score }}</span>
            <span v-if="ts.combos > 0" class="tt-team-combo">+{{ ts.combos }}</span>
          </div>
        </TransitionGroup>

        <div class="tt-sidebar-actions">
          <button type="button" class="tt-action-btn" :disabled="isSpectator || !!challenge" @click="buyPaint">
            <span class="tt-action-icon">+{{ cfg.bundle ?? 3 }}</span>
            <span class="tt-action-meta">{{ cfg.diamond_cost ?? 2 }} 💎</span>
          </button>
          <button
            type="button"
            class="tt-action-btn tt-action-btn--challenge"
            :disabled="isSpectator || !!challenge || challengeBlockedByPaint || (challengeCooldownMs != null && challengeCooldownMs > 0)"
            :title="challengeBlockedByPaint ? t('teamTerritory.toasts.tooMuchPaint', { max: challengeMaxPaint }) : undefined"
            @click="startChallenge"
          >
            <template v-if="challengeCooldownMs != null && challengeCooldownMs > 0">
              {{ Math.ceil(challengeCooldownMs / 1000) }}s
            </template>
            <template v-else>{{ t('teamTerritory.match.challenge') }}</template>
          </button>
        </div>
      </aside>

      <div v-if="phase === 'finished'" class="tt-result-overlay">
        <div class="tt-result card" :class="{ 'tt-result--stale': isVoidMatchFinish }">
          <h2>{{ isVoidMatchFinish ? t('teamTerritory.finish.voidTitle') : t('teamTerritory.finish.title') }}</h2>
          <p class="tt-result-reason">{{ finishReasonLabel(payload?.finish_reason) }}</p>

          <ul class="tt-score-list tt-score-list--board">
            <li
              v-for="row in scoreRows"
              :key="row.id"
              class="tt-score-list-item"
              :class="{ 'tt-score-list-item--mine': row.id === myTeamId }"
              :style="{ '--team-color': row.hex }"
            >
              <span class="tt-score-dot" :style="{ background: row.hex }" />
              <span class="tt-finish-line">
                <strong>{{ row.name }}</strong>
                <span class="tt-finish-total">{{ row.score }}</span>
                <span class="muted tt-finish-breakdown">
                  {{ row.territory }}
                  <template v-if="row.comboBonus > 0"> +{{ row.comboBonus }}</template>
                  <template v-if="row.balanceBonus > 0"> +{{ row.balanceBonus }}</template>
                </span>
              </span>
            </li>
          </ul>

          <p v-if="isVoidMatchFinish" class="muted tt-result-stale-note">
            {{ t('teamTerritory.finish.voidNoReward') }}
          </p>

          <template v-if="!isVoidMatchFinish">
            <p v-if="(payload?.winning_team_ids ?? []).length === 1">
              {{ t('teamTerritory.finish.winners') }}:
              {{ payload?.winning_team_ids?.map((x: number) => teams.find((tm: any) => tm.id === x)?.name ?? x + 1).join(', ') }}
            </p>
            <p v-else-if="isScoreTie" class="muted">{{ t('teamTerritory.finish.tie') }}</p>
            <p v-if="myMatchReward.kind === 'win'" class="tt-reward">
              {{ t('teamTerritory.finish.rewardWin', { diamonds: myMatchReward.diamonds }) }}
            </p>
            <p v-else-if="myMatchReward.kind === 'loss'" class="tt-reward tt-reward--soft">
              {{ t('teamTerritory.finish.rewardLoss', { diamonds: myMatchReward.diamonds }) }}
            </p>
            <p v-else-if="myMatchReward.kind === 'tie'" class="tt-reward tt-reward--soft">
              {{ t('teamTerritory.finish.rewardTie', { diamonds: myMatchReward.diamonds }) }}
            </p>
            <p v-else-if="me.match_rewards_block === 'insufficient_ticks'" class="muted">
              {{ t('teamTerritory.finish.noRewardTicks', { min: cfg.min_ticks_for_reward ?? 3 }) }}
            </p>
            <p v-else class="muted">{{ t('teamTerritory.finish.noReward') }}</p>
          </template>

          <button type="button" class="btn btn-primary" @click="resetLobby">{{ t('teamTerritory.finish.backToLobby') }}</button>
        </div>
      </div>
    </section>

    <div v-if="challenge" class="tt-ch-overlay" :class="{ 'tt-ch-overlay--math': Number(challenge.mode) === 1 }">
      <div
        class="tt-ch card"
        :class="{ 'tt-ch--nomotion': reducedMotion, 'tt-ch--math': Number(challenge.mode) === 1 }"
      >
        <h3>{{ t('teamTerritory.challenge.title') }} · {{ challengeModeLabel(Number(challenge.mode)) }}</h3>
        <p class="muted">{{ challenge.round }} / {{ challenge.max_rounds }}</p>

        <div v-if="showChallengeRoundResult" class="tt-ch-result" :class="lastRoundResult?.success ? 'ok' : 'fail'">
          <p v-if="lastRoundResult?.success && (lastRoundResult?.paint_awarded ?? 0) > 0" class="tt-ch-paint-win">
            <span class="tt-ch-paint-icon">🎨</span>
            {{ t('teamTerritory.challenge.roundSuccess', { paint: lastRoundResult?.paint_awarded ?? 1 }) }}
          </p>
          <p v-else-if="lastRoundResult?.success">{{ t('teamTerritory.challenge.roundOk') }}</p>
          <p v-else>{{ t('teamTerritory.challenge.roundFail') }}</p>
          <p v-if="challengeGapSeconds > 0" class="tt-ch-countdown">
            {{ t('teamTerritory.challenge.countdown', { seconds: challengeGapSeconds }) }}
          </p>
        </div>

        <template v-else-if="!challengeInGap">
          <div v-if="challengeDeadline" class="tt-ch-timer" :class="{ 'tt-ch-timer--urgent': challengeDeadline.urgent }">
            <svg class="tt-ch-timer-ring" viewBox="0 0 72 72" aria-hidden="true">
              <circle class="tt-ch-timer-track" cx="36" cy="36" r="30" />
              <circle
                class="tt-ch-timer-progress"
                cx="36"
                cy="36"
                r="30"
                :style="{ strokeDashoffset: `${188.5 * (1 - challengeDeadline.pct / 100)}` }"
              />
            </svg>
            <span class="tt-ch-timer-num">{{ challengeDeadline.seconds }}</span>
            <span class="tt-ch-timer-label">{{ t('teamTerritory.challenge.deadlineCountdown') }}</span>
          </div>
          <template v-if="Number(challenge.mode) === 1">
            <p class="tt-prompt">{{ challenge.prompt }}</p>
            <input v-model="mathAnswer" class="tt-input" type="number" @keyup.enter="submitChallenge" />
            <button type="button" class="btn btn-primary" @click="submitChallenge">{{ t('teamTerritory.challenge.submit') }}</button>
          </template>
          <template v-else-if="Number(challenge.mode) === 2">
            <p class="tt-prompt">{{ challenge.prompt }}</p>
            <input v-model="spellAnswer" maxlength="1" class="tt-input" @keyup.enter="submitChallenge" />
            <button type="button" class="btn btn-primary" @click="submitChallenge">{{ t('teamTerritory.challenge.letter') }}</button>
          </template>
          <template v-else-if="Number(challenge.mode) === 3">
            <p class="tt-seq-hint">{{ t('teamTerritory.challenge.next') }}: <strong>{{ challenge.sequence_next }}</strong></p>
            <div class="tt-seq-field">
              <button
                v-for="c in challenge.circles ?? []"
                :key="c.id"
                type="button"
                class="tt-seq-btn"
                :style="{ left: `${c.x ?? 50}%`, top: `${c.y ?? 50}%` }"
                @click="tapCircle(Number(c.label))"
              >
                {{ c.label }}
              </button>
            </div>
          </template>
        </template>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="repaintConfirm" class="tt-repaint-backdrop" @click.self="cancelRepaint">
        <div class="tt-repaint-modal card" role="dialog" aria-modal="true">
          <p class="tt-repaint-title">{{ t('teamTerritory.repaint.title') }}</p>
          <p class="tt-repaint-cost">{{ t('teamTerritory.repaint.cost', { cost: repaintCost }) }}</p>
          <div class="tt-repaint-actions">
            <button type="button" class="btn" @click="cancelRepaint">{{ t('teamTerritory.repaint.cancel') }}</button>
            <button type="button" class="btn btn-primary" @click="confirmRepaint">{{ t('teamTerritory.repaint.confirm') }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showGuide" class="guide-backdrop" @click.self="closeGuide">
        <div class="guide-modal" role="dialog" aria-modal="true" aria-labelledby="tt-guide-title">
          <div class="guide-modal-head">
            <h2 id="tt-guide-title" class="guide-title">{{ t('teamTerritory.guide') }}</h2>
            <button type="button" class="guide-close" :aria-label="t('common.close')" @click="closeGuide">×</button>
          </div>
          <div class="guide-body">
            <section v-for="s in guideSections" :key="String(s.title || '')" class="guide-section">
              <h3>{{ s.title }}</h3>
              <div v-if="s.html" v-html="s.html" />
            </section>
          </div>
          <div class="guide-footer">
            <button type="button" class="btn btn-primary" @click="closeGuide">{{ t('teamTerritory.guideOk') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
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
.tt-root--match {
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.tt-root--match .tt-match {
  flex: 1;
  min-height: 0;
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
.tt-toast {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 80;
  max-width: min(420px, calc(100vw - 32px));
  padding: 12px 18px;
  border-radius: 12px;
  background: rgba(46, 125, 50, 0.95);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  text-align: center;
}
.tt-toast--err {
  background: rgba(198, 40, 40, 0.95);
}
.tt-paint-row {
  position: relative;
  display: inline-block;
  transition: transform 0.2s ease;
}
.tt-paint-row--burst {
  animation: tt-paint-pop 0.85s ease-out;
}
.tt-paint-plus {
  position: absolute;
  right: -28px;
  top: -4px;
  color: #a5d6a7;
  font-weight: 800;
  animation: tt-paint-float 0.85s ease-out forwards;
}
@keyframes tt-paint-pop {
  0% { transform: scale(1); }
  35% { transform: scale(1.08); color: #a5d6a7; }
  100% { transform: scale(1); }
}
@keyframes tt-paint-float {
  0% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-18px); }
}
.tt-regen {
  font-size: 0.88rem;
  color: #90caf9;
  margin-top: 2px;
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
.tt-match {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
.tt-match--desktop {
  flex-direction: row;
  align-items: stretch;
  gap: 14px;
}
.tt-board-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  align-items: stretch;
  justify-content: stretch;
}
.tt-match--desktop .tt-board-area {
  justify-content: flex-start;
}
.tt-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 0;
  flex-shrink: 0;
}
.tt-match--desktop .tt-sidebar {
  width: 462px;
  max-height: calc(100vh - 88px);
  overflow-y: auto;
}
.tt-stat {
  display: flex;
  align-items: center;
  gap: 10px;
}
.tt-stat--tick {
  gap: 12px;
}
.tt-stat-ring {
  position: relative;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}
.tt-stat-ring svg {
  width: 44px;
  height: 44px;
  transform: rotate(-90deg);
}
.tt-stat-ring-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.12);
  stroke-width: 4;
}
.tt-stat-ring-fill {
  fill: none;
  stroke: #64b5f6;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 113;
  transition: stroke-dashoffset 0.25s linear;
}
.tt-stat-ring-num {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 0.82rem;
  font-variant-numeric: tabular-nums;
}
.tt-stat-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.tt-stat-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.65;
}
.tt-stat-value {
  font-size: 1.15rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.tt-stat-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: #90caf9;
  margin-top: 4px;
}
.tt-regen-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64b5f6;
  animation: tt-pulse 1.4s ease-in-out infinite;
}
.tt-paint-meter {
  position: relative;
  width: 100%;
  height: 28px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.12);
  overflow: hidden;
}
.tt-paint-meter-fill {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: linear-gradient(90deg, #5c6bc0, #7e57c2);
  border-radius: 999px;
  transition: width 0.3s ease;
}
.tt-paint-meter-text {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-weight: 700;
  font-size: 0.82rem;
  font-variant-numeric: tabular-nums;
}
.tt-paint-meter--burst {
  animation: tt-paint-pop 0.85s ease-out;
}
.tt-stat--ink .tt-stat-icon {
  font-size: 1.25rem;
}
.tt-stall-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 152, 0, 0.14);
  border: 1px solid rgba(255, 152, 0, 0.35);
  color: #ffcc80;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.tt-teams-board {
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
}
.tt-team-rank-move {
  transition: transform 700ms cubic-bezier(0.22, 1, 0.36, 1);
}
.tt-team-rank-enter-active,
.tt-team-rank-leave-active {
  transition: opacity 400ms ease;
}
.tt-team-rank-enter-from,
.tt-team-rank-leave-to {
  opacity: 0;
}
.tt-team-row {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.tt-team-row--mine {
  border-color: var(--team-color, rgba(255, 255, 255, 0.35));
  box-shadow: inset 3px 0 0 var(--team-color, #fff);
  background: rgba(255, 255, 255, 0.06);
}
.tt-team-swatch {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  flex-shrink: 0;
}
.tt-team-name {
  font-size: 0.82rem;
  opacity: 0.88;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tt-team-score {
  font-size: 1.45rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.tt-team-combo {
  font-size: 0.72rem;
  opacity: 0.75;
  color: #ce93d8;
}
.tt-sidebar-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: auto;
}
.tt-action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-height: 52px;
  padding: 8px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.07);
  color: inherit;
  cursor: pointer;
  font-weight: 700;
  font-size: 0.88rem;
}
.tt-action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.tt-action-btn--challenge {
  background: linear-gradient(135deg, rgba(57, 73, 171, 0.55), rgba(92, 107, 192, 0.45));
}
.tt-action-icon {
  font-size: 1.1rem;
}
.tt-action-meta {
  font-size: 0.72rem;
  opacity: 0.8;
}
.tt-invite {
  width: 100%;
  margin-top: 10px;
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
.tt-grid-wrap--fit {
  overflow: visible;
  max-height: none;
  margin-bottom: 0;
  padding: 10px;
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.tt-match--desktop .tt-grid-wrap--fit {
  max-height: none;
}
.tt-grid-wrap--dense .tt-cell {
  min-width: 22px;
  min-height: 22px;
}
.tt-grid {
  display: grid;
  width: fit-content;
}
.tt-cell {
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.25);
  cursor: pointer;
  transition: transform 0.15s ease-out, box-shadow 0.15s;
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
@property --tt-claim-angle {
  syntax: '<angle>';
  initial-value: 0deg;
  inherits: false;
}
.tt-cell--claimed::before {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 6px;
  padding: 3px;
  background: var(--tt-claim-gradient, #fff);
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  z-index: 2;
  animation: tt-claim-gradient-spin 2.2s linear infinite;
}
.tt-cell--repaintable:not(:disabled) {
  cursor: crosshair;
}
.tt-cell--repaintable:not(:disabled):hover {
  filter: brightness(1.12);
}
.tt-repaint-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.45);
}
.tt-repaint-modal {
  width: min(300px, 100%);
  text-align: center;
  margin-bottom: 0;
  padding: 18px 16px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
}
.tt-repaint-title {
  margin: 0 0 8px;
  font-weight: 700;
  font-size: 1rem;
}
.tt-repaint-cost {
  margin: 0 0 16px;
  font-size: 1.2rem;
  font-weight: 800;
  color: #90caf9;
  font-variant-numeric: tabular-nums;
}
.tt-repaint-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}
.tt-repaint-actions .btn {
  min-width: 108px;
}
.tt-cell-label {
  position: relative;
  z-index: 4;
  font-size: 0.58rem;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.94);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
  pointer-events: none;
  line-height: 1;
}
@keyframes tt-claim-gradient-spin {
  to {
    --tt-claim-angle: 360deg;
  }
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
.tt-ch-overlay--math {
  background: rgba(0, 0, 0, 0.75);
}
.tt-ch {
  max-width: 520px;
  width: 100%;
}
.tt-ch--math {
  background: rgba(16, 22, 40, 0.92);
  border-color: rgba(255, 255, 255, 0.22);
}
.tt-ch-timer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin: 8px 0 14px;
  position: relative;
}
.tt-ch-timer-ring {
  width: 72px;
  height: 72px;
  transform: rotate(-90deg);
}
.tt-ch-timer-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.12);
  stroke-width: 6;
}
.tt-ch-timer-progress {
  fill: none;
  stroke: #64b5f6;
  stroke-width: 6;
  stroke-linecap: round;
  stroke-dasharray: 188.5;
  transition: stroke-dashoffset 0.25s linear;
}
.tt-ch-timer--urgent .tt-ch-timer-progress {
  stroke: #ff7043;
}
.tt-ch-timer-num {
  position: absolute;
  top: 22px;
  font-size: 1.5rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.tt-ch-timer-label {
  font-size: 0.8rem;
  color: var(--muted, #9aa0b4);
}
.tt-ch-paint-win {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 1.1rem;
  animation: tt-paint-pop 0.6s ease-out;
}
.tt-ch-paint-icon {
  font-size: 1.4rem;
}
.tt-seq-hint {
  text-align: center;
  margin-bottom: 8px;
}
.tt-seq-field {
  position: relative;
  width: 100%;
  min-height: 320px;
  margin-top: 8px;
  border-radius: 14px;
  background: rgba(10, 16, 32, 0.65);
  border: 1px dashed rgba(255, 255, 255, 0.18);
  overflow: hidden;
}
.tt-seq-btn {
  position: absolute;
  width: 72px;
  height: 72px;
  margin: -36px 0 0 -36px;
  border-radius: 50%;
  font-weight: 800;
  font-size: 1.65rem;
  border: 3px solid rgba(255, 255, 255, 0.4);
  background: rgba(30, 50, 90, 0.92);
  color: inherit;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
  transition: transform 0.12s ease, opacity 0.2s ease;
}
.tt-seq-btn:hover {
  transform: scale(1.06);
  border-color: rgba(255, 255, 255, 0.65);
}
.tt-seq-btn:active {
  transform: scale(0.94);
}
.tt-ch--nomotion .tt-seq-btn {
  transition: none;
}
.tt-prompt {
  font-size: 1.4rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.tt-lobby-hint {
  margin-top: 6px;
  line-height: 1.45;
}
.tt-lobby-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.tt-lobby-head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.btn-guide-tiny {
  height: 34px;
  padding: 0 12px;
  font-size: 0.82rem;
  font-weight: 600;
  border-radius: 999px;
  background: rgba(100, 130, 255, 0.18);
  border: 1px solid rgba(130, 160, 255, 0.45);
  color: #c5d4ff;
}
.btn-guide-tiny:hover {
  background: rgba(100, 130, 255, 0.28);
}
.guide-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(5, 9, 20, 0.75);
  backdrop-filter: blur(10px);
}
.guide-modal {
  width: min(520px, 100%);
  max-height: min(88vh, 720px);
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  background: linear-gradient(165deg, rgba(18, 26, 48, 0.98), rgba(10, 14, 28, 0.99));
  border: 1px solid rgba(130, 160, 255, 0.3);
  box-shadow: 0 28px 56px rgba(0, 0, 0, 0.5);
}
.guide-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.guide-title {
  margin: 0;
  font-size: 1.2rem;
}
.guide-close {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: inherit;
  font-size: 1.4rem;
  line-height: 1;
  cursor: pointer;
}
.guide-close:hover {
  background: rgba(255, 255, 255, 0.14);
}
.guide-body {
  overflow-y: auto;
  padding: 12px 18px 8px;
  flex: 1;
}
.guide-section {
  margin-bottom: 16px;
}
.guide-section h3 {
  margin: 0 0 8px;
  font-size: 1rem;
  color: #b8c4ff;
}
.guide-section :deep(p) {
  margin: 0 0 8px;
  line-height: 1.5;
}
.guide-section :deep(ul) {
  margin: 0;
  padding-left: 1.2rem;
}
.guide-section :deep(li) {
  margin-bottom: 6px;
  line-height: 1.45;
}
.guide-section :deep(.guide-tip) {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(76, 175, 80, 0.12);
  border-left: 3px solid #81c784;
}
.guide-footer {
  padding: 12px 18px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: flex-end;
}
.tt-lobby-title {
  margin: 0;
  font-size: 1.35rem;
}
.tt-lobby-sub {
  margin: 4px 0 0;
  color: var(--muted, #9aa0b4);
  font-size: 0.9rem;
}
.tt-lobby-badge {
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 0.85rem;
  font-weight: 600;
  background: rgba(255, 193, 7, 0.15);
  color: #ffcc80;
  border: 1px solid rgba(255, 193, 7, 0.35);
}
.tt-lobby-badge--ok {
  background: rgba(76, 175, 80, 0.15);
  color: #a5d6a7;
  border-color: rgba(76, 175, 80, 0.35);
}
.tt-lobby-section {
  margin-top: 18px;
}
.tt-lobby-section-title {
  margin: 0 0 10px;
  font-size: 0.95rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted, #9aa0b4);
}
.tt-team-picker {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}
.tt-team-pick {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 2px solid rgba(255, 255, 255, 0.12);
  background: rgba(20, 28, 50, 0.75);
  color: inherit;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.12s, box-shadow 0.15s;
  text-align: left;
}
.tt-team-pick:hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.28);
  transform: translateY(-1px);
}
.tt-team-pick--active {
  border-color: rgba(255, 255, 255, 0.55);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.15);
}
.tt-team-pick--locked {
  opacity: 0.65;
  cursor: not-allowed;
}
.tt-team-pick-swatch {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}
.tt-team-pick-name {
  font-weight: 700;
  font-size: 1rem;
}
.tt-team-pick-meta {
  font-size: 0.8rem;
  color: var(--muted, #9aa0b4);
}
.tt-lobby-roster {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 20px;
}
@media (max-width: 640px) {
  .tt-lobby-roster {
    grid-template-columns: 1fr;
  }
}
.tt-roster-col {
  border-radius: 12px;
  padding: 12px 14px;
  background: rgba(15, 22, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.tt-roster-col--mine {
  border-color: rgba(255, 255, 255, 0.18);
}
.tt-roster-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 0.95rem;
  font-weight: 700;
}
.tt-opponent-total {
  font-weight: 400;
  font-size: 0.85rem;
}
.tt-roster-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.tt-roster-list--compact .tt-roster-item {
  padding: 4px 0;
}
.tt-roster-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.tt-roster-item:last-child {
  border-bottom: none;
}
.tt-roster-item--ready .tt-roster-name,
.tt-roster-item--ready > span:first-child {
  font-weight: 600;
}
.tt-roster-empty {
  padding: 8px 0;
  font-size: 0.9rem;
}
.tt-you {
  font-size: 0.8rem;
  color: var(--muted, #9aa0b4);
  font-weight: 400;
}
.tt-opponent-block {
  margin-bottom: 12px;
}
.tt-opponent-block:last-child {
  margin-bottom: 0;
}
.tt-opponent-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0 6px 8px;
  border-left: 3px solid #666;
  font-size: 0.88rem;
  font-weight: 600;
  margin-bottom: 4px;
}
.tt-lobby-warn {
  margin: 14px 0 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 152, 0, 0.12);
  color: #ffcc80;
  font-size: 0.9rem;
}
.tt-ready {
  width: 100%;
  margin-top: 16px;
  padding: 12px 20px;
  font-size: 1.05rem;
  font-weight: 700;
}
.tt-ready--cancel {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.25);
}
.tt-ink-row {
  font-size: 0.85rem;
}
.tt-team-scores {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 4px;
}
.tt-score-pill {
  border: 2px solid transparent;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
.tt-score-list {
  list-style: none;
  padding: 0;
  margin: 12px 0;
}
.tt-score-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.tt-score-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}
.tt-reward {
  color: #a5d6a7;
  font-weight: 700;
}
.tt-reward--soft {
  color: #90caf9;
  font-weight: 600;
}
.tt-result-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.62);
  backdrop-filter: blur(4px);
}
.tt-result-overlay .tt-result {
  max-width: 480px;
  width: 100%;
  max-height: min(90vh, 720px);
  overflow-y: auto;
  margin-bottom: 0;
}
.tt-result-reason {
  margin: 0 0 12px;
  opacity: 0.88;
}
.tt-result-stale-note {
  margin: 8px 0 16px;
  text-align: center;
}
.tt-score-list--board .tt-score-list-item {
  padding: 10px 8px;
  border-radius: 10px;
  margin-bottom: 6px;
  background: rgba(0, 0, 0, 0.2);
}
.tt-score-list-item--mine {
  box-shadow: inset 3px 0 0 var(--team-color, #fff);
  background: rgba(255, 255, 255, 0.06);
}
.tt-finish-total {
  font-size: 1.35rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.tt-finish-breakdown {
  font-size: 0.78rem;
}
.tt-result--stale {
  border-color: rgba(255, 183, 77, 0.45);
  background: rgba(255, 152, 0, 0.06);
}
.tt-result-stale {
  margin: 16px 0;
  padding: 14px 16px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.2);
  text-align: center;
}
.tt-result-stale-title {
  margin: 0 0 6px;
  font-size: 1.05rem;
  font-weight: 600;
}
.tt-ch-result.ok {
  color: #a5d6a7;
}
.tt-ch-result.fail {
  color: #ffab91;
}
.tt-ch-countdown {
  font-size: 1.5rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.tt-cell--picked {
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.75);
  transform: scale(1.06);
}
.tt-cell--combo {
  position: relative;
  z-index: 2;
  opacity: 1;
  border: 3px solid var(--tt-neon-bright, var(--tt-neon, #fff));
  outline: 2px solid var(--tt-neon-glow, var(--tt-neon, #fff));
  outline-offset: 0;
  box-shadow:
    0 0 0 1px var(--tt-neon-bright, var(--tt-neon, #fff)),
    0 0 0 3px var(--tt-neon-glow, var(--tt-neon, #fff)),
    0 0 5px var(--tt-neon-glow, var(--tt-neon, #fff)),
    0 0 13px var(--tt-neon-soft, var(--tt-neon, #fff)),
    0 0 26px var(--tt-neon-faint, var(--tt-neon, #fff)),
    inset 0 0 10px var(--tt-neon-faint, var(--tt-neon, #fff));
  animation: tt-combo-neon 2.2s ease-in-out infinite;
}
.tt-cell--combo.tt-cell--picked {
  outline: 2px solid rgba(255, 255, 255, 0.9);
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.9),
    0 0 0 4px var(--tt-neon-bright, var(--tt-neon, #fff)),
    0 0 8px var(--tt-neon-glow, var(--tt-neon, #fff)),
    0 0 18px var(--tt-neon-soft, var(--tt-neon, #fff)),
    0 0 31px var(--tt-neon-faint, var(--tt-neon, #fff));
}
@keyframes tt-combo-neon {
  0%,
  100% {
    border-color: var(--tt-neon-bright, var(--tt-neon, #fff));
    outline-color: var(--tt-neon-glow, var(--tt-neon, #fff));
    box-shadow:
      0 0 0 1px var(--tt-neon-bright, var(--tt-neon, #fff)),
      0 0 0 3px var(--tt-neon-glow, var(--tt-neon, #fff)),
      0 0 5px var(--tt-neon-glow, var(--tt-neon, #fff)),
      0 0 16px var(--tt-neon-soft, var(--tt-neon, #fff)),
      0 0 26px var(--tt-neon-faint, var(--tt-neon, #fff));
  }
  50% {
    border-color: #fff;
    outline-color: var(--tt-neon-bright, var(--tt-neon, #fff));
    box-shadow:
      0 0 0 2px #fff,
      0 0 0 5px var(--tt-neon-bright, var(--tt-neon, #fff)),
      0 0 10px var(--tt-neon, #fff),
      0 0 23px var(--tt-neon-soft, var(--tt-neon, #fff)),
      0 0 42px var(--tt-neon-faint, var(--tt-neon, #fff)),
      0 0 57px var(--tt-neon-faint, var(--tt-neon, #fff));
  }
}
.tt-combo-mini {
  font-size: 0.72rem;
  opacity: 0.85;
  margin-left: 4px;
}
.tt-combo-hud {
  font-size: 0.88rem;
  margin-top: 4px;
  color: #b39ddb;
}
.tt-finish-line {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
@media (max-width: 900px) {
  .tt-root--match {
    height: auto;
    overflow: auto;
  }
  .tt-match--desktop .tt-sidebar {
    width: 100%;
    max-height: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .tt-cell.pulse {
    animation: none;
  }
  .tt-cell--combo {
    animation: none;
    outline-width: 2px;
  }
  .tt-cell--claimed::before {
    animation: none;
  }
  .tt-cell:not(:disabled):hover {
    transform: none;
  }
  .tt-team-rank-move {
    transition: none;
  }
}
</style>
