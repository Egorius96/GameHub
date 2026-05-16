<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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

const { state, move, ability, restart } = useGameSocket(auth.token, mode)

const keyHandler = (e: KeyboardEvent) => {
  startGameMusic()
  const isPvp = mode === 'pvp_local'
  const arrowPlayer = isPvp ? 2 : 1
  if (
    ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) ||
    ['KeyW', 'KeyA', 'KeyS', 'KeyD'].includes(e.code)
  ) {
    e.preventDefault()
  }
  if (e.code === 'KeyW') move('up', 1)
  if (e.code === 'KeyS') move('down', 1)
  if (e.code === 'KeyA') move('left', 1)
  if (e.code === 'KeyD') move('right', 1)

  if (e.key === 'ArrowUp') move('up', arrowPlayer)
  if (e.key === 'ArrowDown') move('down', arrowPlayer)
  if (e.key === 'ArrowLeft') move('left', arrowPlayer)
  if (e.key === 'ArrowRight') move('right', arrowPlayer)

  if (e.code === 'KeyE') ability('drugs')
  if (e.code === 'KeyQ') ability('immue')
  if (e.code === 'KeyR') ability('rockspeed')
  if (e.code === 'KeyT') ability('hearty_rock')
}

const keyUpHandler = (e: KeyboardEvent) => {
  const isPvp = mode === 'pvp_local'
  const arrowPlayer = isPvp ? 2 : 1
  if (e.key.startsWith('Arrow') || ['KeyW', 'KeyA', 'KeyS', 'KeyD'].includes(e.code)) e.preventDefault()
  if (['KeyW', 'KeyA', 'KeyS', 'KeyD'].includes(e.code)) move('stop', 1)
  if (e.key.startsWith('Arrow')) move('stop', arrowPlayer)
}

onMounted(() => {
  sceneEl.value?.focus()
  sceneEl.value?.addEventListener('keydown', keyHandler)
  sceneEl.value?.addEventListener('keyup', keyUpHandler)
  window.addEventListener('keydown', keyHandler, { capture: true })
  window.addEventListener('keyup', keyUpHandler, { capture: true })
})

startHeartbeat(auth.token, 'misha_pro_racing_game')
startPresencePing(auth.token, 'misha_pro_racing_game')
onBeforeUnmount(() => {
  sceneEl.value?.removeEventListener('keydown', keyHandler)
  sceneEl.value?.removeEventListener('keyup', keyUpHandler)
  window.removeEventListener('keydown', keyHandler, { capture: true } as any)
  window.removeEventListener('keyup', keyUpHandler, { capture: true } as any)
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
    startGameMusic()

    const lives = Number(s.player1?.lives ?? 0)
    if (prevLives.value !== null && lives < prevLives.value && lives > 0) playProRacingSfx('rock')
    if (!gameOverSfxPlayed.value && prevLives.value !== null && prevLives.value > 0 && lives <= 0) {
      playProRacingSfx('gameover')
      gameOverSfxPlayed.value = true
    }
    prevLives.value = lives

    const dc = Number(s.diamonds_collected ?? 0)
    if (dc > prevDiamCollected.value) playProRacingSfx('diamond')
    prevDiamCollected.value = dc

    if (s.game_over) {
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

/** Как в pro_racing_v3.0.py: шаг 230px по X, скорость 2px/кадр при ~30 тиках/с → ~60px/с */
const LANE_CYCLE_PX = 230
const LANE_SCROLL_PX_PER_SEC = 60
const laneDashDurationSec = LANE_CYCLE_PX / LANE_SCROLL_PX_PER_SEC

const hudLine = computed(() => {
  if (!state.value) return ''
  const p1 = state.value.player1
  const p2 = state.value.player2
  return mode === 'pvp_local'
    ? `P1 ❤ ${p1?.lives ?? 0} · P2 ❤ ${p2?.lives ?? 0} · ${state.value.seconds} с`
    : `❤ ${p1?.lives ?? 0} · ${state.value.seconds} с`
})

function restartGame() {
  playProRacingSfx('button')
  showGameOver.value = false
  prevLives.value = null
  prevDiamCollected.value = 0
  gameOverSfxPlayed.value = false
  startGameMusic()
  restart()
}

function backToMenu() {
  playProRacingSfx('button')
  stopMusic()
  router.push('/menu')
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
        <div v-if="state" class="pr-game-hud">
          <span class="pr-game-hud-line">{{ hudLine }}</span>
          <span class="pr-game-hud-diamonds">
            <img src="/assets/original/brilliant.png" alt="" width="22" height="14" />
            {{ (auth.otherData as any).diamonds ?? 0 }}
          </span>
        </div>
      </header>

      <section class="pr-game-panel">
        <div v-if="state" class="pr-scene-wrap">
          <div
            ref="sceneEl"
            tabindex="0"
            class="pr-scene"
            :class="{ 'pr-scene--paused': showGameOver }"
            :style="{ '--lane-dash-dur': `${laneDashDurationSec}s` }"
            role="application"
            aria-label="Игровое поле"
          >
            <div class="pr-scene-bg" aria-hidden="true" />

            <!-- Разметка как в оригинале: горизонтальные белые полосы 150×25, шаг 230px, едут влево -->
            <div class="pr-road" aria-hidden="true">
              <div class="pr-road-vignette" />
              <div class="pr-lane-strip">
                <div class="pr-lane-dashes" />
              </div>
            </div>

            <div class="pr-layer-ui">
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
          </div>
        </div>

        <p class="pr-hint">
          <template v-if="mode === 'pvp_local'">Игрок 1: <kbd>WASD</kbd> · Игрок 2: <kbd>стрелки</kbd></template>
          <template v-else>Управление: <kbd>WASD</kbd> или кнопки ниже</template>
          · Способности: <kbd>E</kbd> <kbd>Q</kbd> <kbd>R</kbd> <kbd>T</kbd>
        </p>

        <div class="pr-pad">
          <span />
          <button type="button" class="pr-pad-btn" @click="move('up')">▲</button>
          <span />
          <button type="button" class="pr-pad-btn" @click="move('left')">◀</button>
          <button type="button" class="pr-pad-btn pr-pad-btn--mid" @click="move('down')">▼</button>
          <button type="button" class="pr-pad-btn" @click="move('right')">▶</button>
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
      </section>
    </div>
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
  border-radius: 18px;
  padding: 14px;
  background: rgba(10, 14, 28, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.pr-scene-wrap {
  border-radius: 14px;
  overflow: hidden;
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
  animation: pr-lane-scroll var(--lane-dash-dur, 3.83s) linear infinite;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
}
@keyframes pr-lane-scroll {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-230px);
  }
}
.pr-scene--paused .pr-lane-dashes {
  animation-play-state: paused;
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
</style>
