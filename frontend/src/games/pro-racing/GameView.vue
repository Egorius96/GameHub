<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useGameSocket } from './useGameSocket'
import {
  playProRacingSfx,
  startGameMusic,
  stopGameMusicOnly,
  stopMusic,
} from '../../audio/sound'
import { proRacingMusicEnabled } from './audioSettings'
import { startHeartbeat, stopHeartbeat } from '../../telemetry/heartbeat'
import { startPresencePing, stopPresencePing } from '../../telemetry/presence'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const mode = String(route.params.mode || 'normal')
const gameData = computed(() => ((auth.otherData as any).games ?? {})?.misha_pro_racing_game ?? {})
const carLevel = computed(() => Number((gameData.value as any).car_level ?? 1))
const sceneEl = ref<HTMLDivElement | null>(null)
const diamondHudRef = ref<HTMLElement | null>(null)
const SCENE_W = 1200
const SCENE_H = 700
const BASE_ROCK_SPEED = 10
const BASE_KMH = 60
type DiamondFlight = { id: string; x0: number; y0: number; x1: number; y1: number }
const diamondFlights = ref<DiamondFlight[]>([])
const lastVisibleDiamond = ref<{ x: number; y: number } | null>(null)
const secondsPulse = ref(false)
let secondsPulseTimer: number | null = null
const displaySeconds = ref(0)

const modeTitle = computed(() => {
  if (mode === 'hard') return 'Сложный режим'
  if (mode === 'pvp_local') return 'Два игрока'
  return 'Обычный режим'
})

const carImageByLevel: Record<number, string> = {
  1: '/assets/original/car_lvl1.png',
  2: '/assets/original/car_lvl2.png',
  3: '/assets/original/car_lvl3.png',
}
const carShieldImageByLevel: Record<number, string> = {
  1: '/assets/original/car_lvl1_shield.png',
  2: '/assets/original/car_lvl2_shield.png',
  3: '/assets/original/car_lvl3_shield.png',
}

const { state, wsError, connected, move, ability, restart, reconnect, disconnect, gameOver } =
  useGameSocket(auth.token, mode)

const ignoreGameOverUntil = ref(0)

type MoveKey = 'up' | 'down' | 'left' | 'right'
const keysP1 = new Set<MoveKey>()
const keysP2 = new Set<MoveKey>()

function keysToVector(keys: Set<MoveKey>): { dx: number; dy: number } {
  let dx = 0
  let dy = 0
  if (keys.has('left')) dx -= 1
  if (keys.has('right')) dx += 1
  if (keys.has('up')) dy -= 1
  if (keys.has('down')) dy += 1
  return { dx, dy }
}

function syncMovement(player: 1 | 2) {
  const keys = player === 1 ? keysP1 : keysP2
  const { dx, dy } = keysToVector(keys)
  move(dx, dy, player)
}

function setKeyHeld(key: MoveKey, player: 1 | 2, held: boolean) {
  const keys = player === 1 ? keysP1 : keysP2
  if (held) keys.add(key)
  else keys.delete(key)
  syncMovement(player)
}

function keyFromEvent(e: KeyboardEvent): { key: MoveKey; player: 1 | 2 } | null {
  const isPvp = mode === 'pvp_local'
  if (e.code === 'KeyW') return { key: 'up', player: 1 }
  if (e.code === 'KeyS') return { key: 'down', player: 1 }
  if (e.code === 'KeyA') return { key: 'left', player: 1 }
  if (e.code === 'KeyD') return { key: 'right', player: 1 }
  if (e.key === 'ArrowUp') return { key: 'up', player: isPvp ? 2 : 1 }
  if (e.key === 'ArrowDown') return { key: 'down', player: isPvp ? 2 : 1 }
  if (e.key === 'ArrowLeft') return { key: 'left', player: isPvp ? 2 : 1 }
  if (e.key === 'ArrowRight') return { key: 'right', player: isPvp ? 2 : 1 }
  return null
}

const keyHandler = (e: KeyboardEvent) => {
  startGameMusic()
  const mapped = keyFromEvent(e)
  if (mapped) {
    e.preventDefault()
    setKeyHeld(mapped.key, mapped.player, true)
  }

  if (e.code === 'KeyE') ability('drugs')
  if (e.code === 'KeyQ') ability('immue')
  if (e.code === 'KeyR') ability('rockspeed')
  if (e.code === 'KeyT') ability('hearty_rock')
}

const keyUpHandler = (e: KeyboardEvent) => {
  const mapped = keyFromEvent(e)
  if (mapped) {
    e.preventDefault()
    setKeyHeld(mapped.key, mapped.player, false)
  }
}

function padHold(key: MoveKey, held: boolean) {
  setKeyHeld(key, 1, held)
}

onMounted(() => {
  sceneEl.value?.focus()
  window.addEventListener('keydown', keyHandler)
  window.addEventListener('keyup', keyUpHandler)
  laneLastTs = 0
  laneRafId = requestAnimationFrame(tickLaneScroll)
})

startHeartbeat(auth.token, 'misha_pro_racing_game')
startPresencePing(auth.token, 'misha_pro_racing_game')
onBeforeUnmount(() => {
  if (laneRafId) cancelAnimationFrame(laneRafId)
  window.removeEventListener('keydown', keyHandler)
  window.removeEventListener('keyup', keyUpHandler)
  if (secondsPulseTimer) window.clearTimeout(secondsPulseTimer)
  stopMusic()
  stopHeartbeat()
  stopPresencePing()
})

watch(proRacingMusicEnabled, (on) => {
  if (on) startGameMusic()
  else stopGameMusicOnly()
})

const prevLives = ref<number | null>(null)
const prevDiamCollected = ref<number>(0)
const showGameOver = ref(false)
const gameOverSfxPlayed = ref(false)

watch(
  state,
  async (s) => {
    if (!s) return
    await nextTick()
    sceneEl.value?.focus()
    startGameMusic()

    const lives = Number(s.player1?.lives ?? 0)
    if (prevLives.value !== null && lives < prevLives.value && lives > 0) playProRacingSfx('rock')
    if (!gameOverSfxPlayed.value && prevLives.value !== null && prevLives.value > 0 && lives <= 0) {
      playProRacingSfx('gameover')
      gameOverSfxPlayed.value = true
    }
    prevLives.value = lives

    const d = s.diamond as { x?: number; y?: number } | undefined
    if (d && Number(d.x) > -100) {
      lastVisibleDiamond.value = { x: Number(d.x), y: Number(d.y) }
    }

    const sec = Number(s.seconds ?? 0)
    if (sec !== displaySeconds.value) {
      displaySeconds.value = sec
      secondsPulse.value = true
      if (secondsPulseTimer) window.clearTimeout(secondsPulseTimer)
      secondsPulseTimer = window.setTimeout(() => {
        secondsPulse.value = false
        secondsPulseTimer = null
      }, 450)
    }

    const dc = Number(s.diamonds_collected ?? 0)
    if (dc > prevDiamCollected.value) {
      playProRacingSfx('diamond')
      const pos = lastVisibleDiamond.value
      if (pos) launchDiamondFlyFromGame(pos.x + 50, pos.y + 30)
      else launchDiamondFlyFromGame(Number(s.player1?.x ?? 600) + 75, Number(s.player1?.y ?? 350))
    }
    prevDiamCollected.value = dc

    if (s.game_over && Date.now() >= ignoreGameOverUntil.value) {
      showGameOver.value = true
      if (!gameOverSfxPlayed.value) {
        playProRacingSfx('gameover')
        gameOverSfxPlayed.value = true
      }
      await auth.refreshProfile()
      stopGameMusicOnly()
    }
  },
  { deep: true },
)

/** Как в pro_racing_v3.0.py: шаг 230px по X; скролл полосы привязан к speed_rock (60 км/ч при 10) */
const LANE_CYCLE_PX = 230
const LANE_SCROLL_BASE_PX_PER_SEC = 60

const rockSpeed = computed(() => Number(state.value?.speed_rock ?? BASE_ROCK_SPEED))

const displayKmh = computed(() =>
  Math.round(BASE_KMH * (rockSpeed.value / BASE_ROCK_SPEED))
)

/** Смещение полос: rAF вместо CSS-animation — иначе при каждом тике WS сбрасывается анимация */
const laneOffsetPx = ref(0)
let laneRafId = 0
let laneLastTs = 0

function laneScrollPxPerSec(): number {
  return LANE_SCROLL_BASE_PX_PER_SEC * (rockSpeed.value / BASE_ROCK_SPEED)
}

function tickLaneScroll(ts: number) {
  if (!laneLastTs) laneLastTs = ts
  const dt = Math.min((ts - laneLastTs) / 1000, 0.05)
  laneLastTs = ts
  if (state.value && !showGameOver.value) {
    laneOffsetPx.value = (laneOffsetPx.value + laneScrollPxPerSec() * dt) % LANE_CYCLE_PX
  }
  laneRafId = requestAnimationFrame(tickLaneScroll)
}

const hudLine = computed(() => {
  if (!state.value) return ''
  const p1 = state.value.player1
  const p2 = state.value.player2
  return mode === 'pvp_local'
    ? `P1 ❤ ${p1?.lives ?? 0} · P2 ❤ ${p2?.lives ?? 0}`
    : `❤ ${p1?.lives ?? 0}`
})

function gameToScreen(gx: number, gy: number): { x: number; y: number } {
  const el = sceneEl.value
  if (!el) return { x: window.innerWidth / 2, y: window.innerHeight / 2 }
  const r = el.getBoundingClientRect()
  const sx = r.width / SCENE_W
  const sy = r.height / SCENE_H
  return { x: r.left + gx * sx, y: r.top + gy * sy }
}

function launchDiamondFlyFromGame(gx: number, gy: number) {
  void nextTick(() => {
    const hud = diamondHudRef.value
    if (!hud) return
    const { x: x0, y: y0 } = gameToScreen(gx, gy)
    const hr = hud.getBoundingClientRect()
    const x1 = hr.left + hr.width / 2
    const y1 = hr.top + hr.height / 2
    const id = `pr_df_${Date.now()}`
    diamondFlights.value = [...diamondFlights.value, { id, x0, y0, x1, y1 }]
    window.setTimeout(() => {
      diamondFlights.value = diamondFlights.value.filter((d) => d.id !== id)
      hud.classList.add('pr-game-hud-diamonds--pulse')
      window.setTimeout(() => hud.classList.remove('pr-game-hud-diamonds--pulse'), 520)
    }, 950)
  })
}

function restartGame() {
  playProRacingSfx('button')
  keysP1.clear()
  keysP2.clear()
  ignoreGameOverUntil.value = Date.now() + 800
  showGameOver.value = false
  gameOver.value = false
  prevLives.value = null
  prevDiamCollected.value = 0
  gameOverSfxPlayed.value = false
  displaySeconds.value = 0
  secondsPulse.value = false
  lastVisibleDiamond.value = null
  diamondFlights.value = []
  startGameMusic()
  if (connected.value) {
    restart()
  } else {
    reconnect()
  }
  void nextTick(() => sceneEl.value?.focus())
}

function backToMenu() {
  playProRacingSfx('button')
  keysP1.clear()
  keysP2.clear()
  disconnect()
  stopMusic()
  stopHeartbeat()
  stopPresencePing()
  void router.replace('/menu')
}
</script>

<template>
  <main class="page pr-game-page">
    <div class="pr-game-bg" aria-hidden="true" />

    <div class="pr-game-layout">
      <header class="pr-game-top">
        <div>
          <p class="pr-game-kicker">Pro Racing</p>
          <h1 class="pr-game-title">{{ modeTitle }}</h1>
        </div>
        <div class="pr-top-actions">
          <button type="button" class="pr-btn pr-btn--ghost" @click="restartGame">Рестарт</button>
          <button type="button" class="pr-btn" @click="backToMenu">В меню</button>
        </div>
        <div v-if="state" class="pr-game-hud">
          <span class="pr-game-hud-line">{{ hudLine }}</span>
          <span ref="diamondHudRef" class="pr-game-hud-diamonds" title="Копилка алмазов">
            <img src="/assets/original/brilliant.png" alt="" width="22" height="14" />
            {{ (auth.otherData as any).diamonds ?? 0 }}
          </span>
        </div>
      </header>

      <section class="pr-game-panel">
        <div class="pr-scene-wrap">
          <div
            ref="sceneEl"
            tabindex="0"
            class="pr-scene"
            :class="{
              'pr-scene--paused': showGameOver && !!state,
              'pr-scene--waiting': !state,
            }"
            :style="state ? { '--pr-kmh': displayKmh } : undefined"
            role="application"
            aria-label="Игровое поле"
          >
            <div v-if="!state" class="pr-connect-overlay">
              <p v-if="wsError" class="pr-connect-msg pr-connect-msg--error">{{ wsError }}</p>
              <p v-else class="pr-connect-msg">Подключение к игре…</p>
              <button v-if="wsError" type="button" class="pr-btn pr-btn--primary" @click="reconnect">
                Переподключить
              </button>
            </div>

            <template v-else>
            <div class="pr-scene-bg" aria-hidden="true" />

            <!-- Разметка как в оригинале: горизонтальные белые полосы 150×25, шаг 230px, едут влево -->
            <div class="pr-road" aria-hidden="true">
              <div class="pr-road-vignette" />
              <div class="pr-lane-strip">
                <div
                  class="pr-lane-dashes"
                  :style="{ transform: `translateX(${-laneOffsetPx}px)` }"
                />
              </div>
            </div>

            <div class="pr-layer-ui">
              <div class="pr-run-hud" aria-live="polite">
                <div class="pr-run-time" :class="{ 'pr-run-time--pulse': secondsPulse }">
                  <span class="pr-run-time-label">Время</span>
                  <span class="pr-run-time-value" :key="'sec-' + displaySeconds">{{ displaySeconds }}</span>
                  <span class="pr-run-time-unit">сек</span>
                </div>
                <div class="pr-run-speed">
                  <span class="pr-run-speed-label">Скорость</span>
                  <span class="pr-run-speed-value" :key="'kmh-' + displayKmh">{{ displayKmh }}</span>
                  <span class="pr-run-speed-unit">км/ч</span>
                </div>
              </div>
              <div class="pr-lives pr-lives--p1">
                <img v-for="i in Number(state.player1?.lives ?? 0)" :key="i" src="/assets/original/heart.png" alt="" />
              </div>
              <div v-if="mode === 'pvp_local'" class="pr-lives pr-lives--p2">
                <img v-for="i in Number(state.player2?.lives ?? 0)" :key="'p2' + i" src="/assets/original/heart.png" alt="" />
              </div>
            </div>

            <div class="pr-layer-sprites">
              <img
                class="pr-sprite"
                src="/assets/original/rock.png"
                alt=""
                width="100"
                height="80"
                :style="{ left: `${state.rock1.x}px`, top: `${state.rock1.y}px` }"
              />
              <img
                class="pr-sprite"
                src="/assets/original/rock.png"
                alt=""
                width="100"
                height="80"
                :style="{ left: `${state.rock2.x}px`, top: `${state.rock2.y}px` }"
              />
              <img
                class="pr-sprite"
                src="/assets/original/brilliant.png"
                alt=""
                width="100"
                height="60"
                :style="{ left: `${state.diamond.x}px`, top: `${state.diamond.y}px` }"
              />
              <img
                class="pr-sprite pr-car"
                :src="
                  Number(state.immue_left ?? 0) > 0
                    ? (carShieldImageByLevel[carLevel] ?? carShieldImageByLevel[1])
                    : (carImageByLevel[carLevel] ?? carImageByLevel[1])
                "
                alt=""
                width="150"
                height="68"
                :style="{ left: `${state.player1.x}px`, top: `${state.player1.y}px` }"
              />
              <img
                v-if="mode === 'pvp_local'"
                class="pr-sprite pr-car"
                :src="
                  Number(state.immue_left ?? 0) > 0
                    ? (carShieldImageByLevel[carLevel] ?? carShieldImageByLevel[1])
                    : (carImageByLevel[carLevel] ?? carImageByLevel[1])
                "
                alt=""
                width="150"
                height="68"
                :style="{ left: `${state.player2.x}px`, top: `${state.player2.y}px` }"
              />
            </div>

            <div v-if="showGameOver" class="pr-overlay">
              <div class="pr-modal">
                <h2 class="pr-modal-title">Игра окончена</h2>
                <p class="pr-modal-text">Вы продержались <strong>{{ state.seconds }}</strong> с</p>
                <p v-if="mode === 'pvp_local'" class="pr-modal-text">Победитель: <strong>{{ state.winner }}</strong></p>
                <div class="pr-modal-actions">
                  <button type="button" class="pr-btn pr-btn--ghost" @click="backToMenu">В меню</button>
                  <button type="button" class="pr-btn pr-btn--primary" @click="restartGame">Ещё раз</button>
                </div>
              </div>
            </div>
            </template>
          </div>
        </div>

        <div class="pr-game-chrome">
        <p class="pr-hint">
          <template v-if="mode === 'pvp_local'">Игрок 1: <kbd>WASD</kbd> · Игрок 2: <kbd>стрелки</kbd></template>
          <template v-else>Управление: <kbd>WASD</kbd> или кнопки ниже</template>
          · Способности: <kbd>E</kbd> <kbd>Q</kbd> <kbd>R</kbd> <kbd>T</kbd>
        </p>

        <div class="pr-pad">
          <span />
          <button
            type="button"
            class="pr-pad-btn"
            @mousedown.prevent="padHold('up', true)"
            @mouseup="padHold('up', false)"
            @mouseleave="padHold('up', false)"
            @touchstart.prevent="padHold('up', true)"
            @touchend.prevent="padHold('up', false)"
          >
            ▲
          </button>
          <span />
          <button
            type="button"
            class="pr-pad-btn"
            @mousedown.prevent="padHold('left', true)"
            @mouseup="padHold('left', false)"
            @mouseleave="padHold('left', false)"
            @touchstart.prevent="padHold('left', true)"
            @touchend.prevent="padHold('left', false)"
          >
            ◀
          </button>
          <button
            type="button"
            class="pr-pad-btn pr-pad-btn--mid"
            @mousedown.prevent="padHold('down', true)"
            @mouseup="padHold('down', false)"
            @mouseleave="padHold('down', false)"
            @touchstart.prevent="padHold('down', true)"
            @touchend.prevent="padHold('down', false)"
          >
            ▼
          </button>
          <button
            type="button"
            class="pr-pad-btn"
            @mousedown.prevent="padHold('right', true)"
            @mouseup="padHold('right', false)"
            @mouseleave="padHold('right', false)"
            @touchstart.prevent="padHold('right', true)"
            @touchend.prevent="padHold('right', false)"
          >
            ▶
          </button>
        </div>

        <div class="pr-abilities">
          <button type="button" class="pr-ab" @click="ability('drugs')">Drugs <span class="pr-key">E</span></button>
          <button type="button" class="pr-ab" @click="ability('immue')">Immue <span class="pr-key">Q</span></button>
          <button type="button" class="pr-ab" @click="ability('rockspeed')">Rockspeed <span class="pr-key">R</span></button>
          <button type="button" class="pr-ab" @click="ability('hearty_rock')">Hearty <span class="pr-key">T</span></button>
        </div>

        <div class="pr-footer-actions">
          <button type="button" class="pr-btn pr-btn--ghost" @click="restartGame">Рестарт</button>
          <button type="button" class="pr-btn" @click="backToMenu">В меню</button>
        </div>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <img
        v-for="d in diamondFlights"
        :key="d.id"
        class="pr-diamond-fly"
        src="/assets/original/brilliant.png"
        alt=""
        :style="{
          left: `${d.x0}px`,
          top: `${d.y0}px`,
          '--x1': `${d.x1}px`,
          '--y1': `${d.y1}px`,
        }"
        aria-hidden="true"
      />
    </Teleport>
  </main>
</template>

<style scoped>
.pr-game-page {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
}
.pr-game-bg {
  position: fixed;
  inset: 0;
  background:
    radial-gradient(ellipse 100% 60% at 50% 0%, rgba(80, 120, 255, 0.18), transparent 50%),
    linear-gradient(180deg, #080c18 0%, #0e1424 100%);
  z-index: 0;
  pointer-events: none;
}
.pr-game-layout {
  position: relative;
  z-index: 1;
  max-width: 1240px;
  margin: 0 auto;
  padding: 16px 14px 28px;
}
.pr-game-top {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 14px;
  position: relative;
  z-index: 30;
}
.pr-top-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  pointer-events: auto;
}
.pr-game-kicker {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(150, 180, 255, 0.85);
}
.pr-game-title {
  margin: 0;
  font-size: clamp(1.25rem, 3vw, 1.6rem);
  font-weight: 800;
}
.pr-game-hud {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  padding: 10px 14px;
  border-radius: 14px;
  background: rgba(12, 18, 36, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.pr-game-hud-line {
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.pr-game-hud-diamonds {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 800;
  opacity: 0.95;
}
.pr-game-panel {
  display: flex;
  flex-direction: column;
  border-radius: 18px;
  padding: 14px;
  background: rgba(10, 14, 28, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.pr-scene-wrap {
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  border-radius: 14px;
  overflow: hidden;
  pointer-events: none;
}
.pr-game-chrome {
  position: relative;
  z-index: 20;
  flex: 0 0 auto;
  pointer-events: auto;
}
.pr-scene--waiting {
  background: linear-gradient(180deg, #0c1224 0%, #141c34 100%);
}
.pr-connect-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 24px;
  text-align: center;
  background: rgba(6, 10, 22, 0.88);
}
.pr-connect-msg {
  margin: 0;
  font-size: 15px;
  opacity: 0.9;
  max-width: 360px;
  line-height: 1.45;
}
.pr-connect-msg--error {
  color: #ffab91;
}
.pr-scene {
  position: relative;
  width: 1200px;
  height: 700px;
  max-width: 100%;
  margin: 0 auto;
  overflow: hidden;
  border-radius: 14px;
  outline: none;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.12);
  pointer-events: none;
}
.pr-scene-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  background-image: url('/assets/original/game_background.jpg');
  background-size: cover;
  background-position: center;
}
/* Слой дороги: как в pro_racing_v3.0.py — белые горизонтальные сегменты 150×25, шаг 230px, движение влево */
.pr-road {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}
.pr-road-vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse 95% 75% at 50% 42%, transparent 0%, rgba(0, 0, 0, 0.2) 55%, rgba(0, 0, 0, 0.5) 100%);
  opacity: 0.85;
}
.pr-lane-strip {
  position: absolute;
  left: 0;
  right: 0;
  /* y=335, h=25 при высоте сцены 700px */
  top: 47.857%;
  height: 3.571%;
  min-height: 20px;
  overflow: hidden;
  z-index: 1;
}
.pr-lane-dashes {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 400%;
  background: repeating-linear-gradient(
    90deg,
    #ffffff 0,
    #ffffff 150px,
    transparent 150px,
    transparent 230px
  );
  background-size: 230px 100%;
  will-change: transform;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
}
.pr-layer-ui {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
}
.pr-lives {
  position: absolute;
  left: 12px;
  display: flex;
  gap: 6px;
}
.pr-lives img {
  width: 44px;
  height: 44px;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.6));
}
.pr-lives--p1 {
  top: 10px;
}
.pr-lives--p2 {
  top: 320px;
}
.pr-layer-sprites {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
}
.pr-sprite {
  position: absolute;
  display: block;
  filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.35));
}
.pr-car {
  z-index: 1;
}
.pr-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 8, 18, 0.72);
  backdrop-filter: blur(4px);
  pointer-events: auto;
}
.pr-modal {
  width: min(480px, 92%);
  padding: 22px 22px 18px;
  border-radius: 18px;
  background: linear-gradient(165deg, rgba(22, 32, 58, 0.98), rgba(12, 16, 32, 0.98));
  border: 1px solid rgba(130, 170, 255, 0.28);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
}
.pr-modal-title {
  margin: 0 0 10px;
  font-size: 1.35rem;
  font-weight: 800;
}
.pr-modal-text {
  margin: 0 0 8px;
  font-size: 15px;
  opacity: 0.9;
  line-height: 1.45;
}
.pr-modal-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
  justify-content: flex-end;
}
.pr-hint {
  margin: 12px 0 0;
  font-size: 13px;
  opacity: 0.72;
  line-height: 1.5;
  text-align: center;
}
.pr-hint kbd {
  display: inline-block;
  padding: 2px 7px;
  margin: 0 2px;
  border-radius: 6px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
}
.pr-pad {
  margin-top: 16px;
  display: grid;
  grid-template-columns: 1fr 56px 1fr;
  grid-template-rows: 48px 48px 48px;
  justify-items: center;
  align-items: center;
  max-width: 200px;
  margin-left: auto;
  margin-right: auto;
  gap: 4px;
}
.pr-pad-btn {
  width: 52px;
  height: 48px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.08);
  color: inherit;
  font-size: 1.1rem;
  cursor: pointer;
  transition: background 0.12s ease, transform 0.1s ease;
}
.pr-pad-btn:hover {
  background: rgba(120, 160, 255, 0.22);
}
.pr-pad-btn:active {
  transform: scale(0.96);
}
.pr-pad-btn--mid {
  grid-column: 2;
}
.pr-abilities {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
@media (min-width: 640px) {
  .pr-abilities {
    grid-template-columns: repeat(4, 1fr);
  }
}
.pr-ab {
  padding: 12px 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(18, 26, 48, 0.85);
  color: inherit;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pr-ab:hover {
  border-color: rgba(140, 180, 255, 0.35);
  background: rgba(30, 44, 80, 0.9);
}
.pr-key {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.12);
  font-family: ui-monospace, monospace;
}
.pr-footer-actions {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  pointer-events: auto;
}
.pr-btn {
  padding: 12px 20px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.08);
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  pointer-events: auto;
}
.pr-btn:hover {
  border-color: rgba(140, 170, 255, 0.35);
}
.pr-btn--ghost {
  background: transparent;
}
.pr-btn--primary {
  border-color: rgba(100, 200, 160, 0.45);
  background: linear-gradient(180deg, rgba(120, 220, 170, 0.35), rgba(40, 120, 90, 0.45));
}
.pr-game-hud-diamonds--pulse {
  animation: prHudDiamondPulse 0.5s ease;
}
@keyframes prHudDiamondPulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.14);
  }
}
.pr-run-hud {
  position: absolute;
  top: 10px;
  right: 12px;
  left: auto;
  display: flex;
  flex-direction: row;
  gap: 8px;
  align-items: stretch;
  z-index: 4;
  pointer-events: none;
}
.pr-run-time,
.pr-run-speed {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 92px;
  padding: 8px 12px 6px;
  border-radius: 18px;
  background: rgba(8, 12, 28, 0.78);
  border: 2px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(8px);
}
.pr-run-time {
  border-color: rgba(255, 200, 80, 0.45);
}
.pr-run-time--pulse {
  animation: prTimePulse 0.45s cubic-bezier(0.34, 1.4, 0.64, 1);
}
@keyframes prTimePulse {
  0% {
    transform: scale(1);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
  }
  40% {
    transform: scale(1.08);
    box-shadow: 0 0 36px rgba(255, 193, 7, 0.55);
  }
  100% {
    transform: scale(1);
  }
}
.pr-run-speed {
  border-color: rgba(100, 181, 246, 0.5);
}
.pr-run-time-label,
.pr-run-speed-label {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  opacity: 0.72;
  margin-bottom: 4px;
}
.pr-run-time-value {
  font-size: clamp(1.5rem, 4vw, 2rem);
  font-weight: 900;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: #ffecb3;
  text-shadow: 0 0 28px rgba(255, 193, 7, 0.55);
  animation: prTimeDigitIn 0.35s cubic-bezier(0.34, 1.35, 0.64, 1);
}
.pr-run-time-unit,
.pr-run-speed-unit {
  font-size: 12px;
  font-weight: 700;
  opacity: 0.75;
  margin-top: 2px;
}
.pr-run-speed-value {
  font-size: clamp(1.25rem, 3.5vw, 1.65rem);
  font-weight: 900;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: #90caf9;
  text-shadow: 0 0 20px rgba(66, 165, 245, 0.45);
  transition: color 0.25s ease;
}
@keyframes prTimeDigitIn {
  from {
    transform: scale(0.6);
    opacity: 0.4;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
.pr-diamond-fly {
  position: fixed;
  z-index: 300;
  width: 48px;
  height: auto;
  pointer-events: none;
  transform: translate(-50%, -50%);
  filter: drop-shadow(0 4px 14px rgba(100, 200, 255, 0.85));
  animation: prDiamondFly 0.92s cubic-bezier(0.25, 0.85, 0.35, 1) forwards;
}
@keyframes prDiamondFly {
  0% {
    left: var(--x0, 50%);
    top: var(--y0, 50%);
    transform: translate(-50%, -50%) scale(1.15) rotate(-8deg);
    opacity: 1;
  }
  100% {
    left: var(--x1);
    top: var(--y1);
    transform: translate(-50%, -50%) scale(0.35) rotate(12deg);
    opacity: 0.2;
  }
}
</style>
