<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { apiGet, apiPost } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { startPresencePing, stopPresencePing } from '../../telemetry/presence'

const WIDTH = 1000
const HEIGHT = 600
const SPRITE = 100
const STEP_MS = 1000 / 60
const ASSET = '/assets/games/pumpkin-dodge'
const GAME_KEY = 'pumpkin_dodge'

type Mode = 'menu' | 'game' | 'gameover' | 'top'
type Rect = { x: number; y: number; w: number; h: number }
type Pumpkin = { x: number; y: number; speed: number }

const START_BTN: Rect = { x: 390, y: 115, w: 245, h: 40 }
const TOP_BTN: Rect = { x: 390, y: 195, w: 245, h: 40 }
const EXIT_BTN: Rect = { x: 460, y: 472, w: 100, h: 40 }
const SECRET_BTN: Rect = { x: 0, y: 0, w: 10, h: 10 }
const BACK_BTN: Rect = { x: 0, y: 520, w: 214, h: 75 }

const auth = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const stageRef = ref<HTMLElement | null>(null)
const mode = ref<Mode>('menu')
const seconds = ref(0)
const survived = ref(0)
const diamondsAwarded = ref<number | null>(null)
const saveError = ref('')
const topUsers = ref<Array<{ username: string; other_data?: { games?: Record<string, { high_score_seconds?: number }> } }>>([])
const topLoading = ref(false)

const player = { x: 400, y: 500 }
const pumpkins: Pumpkin[] = []
let hearts = 3
let simMs = 0
let raf = 0
let acc = 0
let lastTs = 0
let finishedPosted = false
let starting = false
let runToken = 0
let startPromise: Promise<boolean> | null = null
const keys = new Set<string>()

const images: Record<string, HTMLImageElement> = {}
let music: HTMLAudioElement | null = null

function loadImage(name: string): Promise<void> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      images[name] = img
      resolve()
    }
    img.onerror = () => resolve()
    img.src = `${ASSET}/${name}.png`
  })
}

function hit(rect: Rect, x: number, y: number): boolean {
  return x >= rect.x && x <= rect.x + rect.w && y >= rect.y && y <= rect.y + rect.h
}

function randX(): number {
  return Math.floor(Math.random() * (WIDTH - SPRITE))
}

function resetPumpkin(p: Pumpkin): void {
  p.x = randX()
  p.y = -SPRITE - Math.random() * 550
}

function resetRun(): void {
  runToken += 1
  startPromise = null
  player.x = 400
  player.y = 500
  hearts = 3
  simMs = 0
  pumpkins.splice(
    0,
    pumpkins.length,
    { x: randX(), y: -SPRITE - Math.random() * 550, speed: 2 },
    { x: randX(), y: -SPRITE - Math.random() * 550, speed: 3 },
    { x: randX(), y: -SPRITE - Math.random() * 550, speed: 4 },
  )
  seconds.value = 0
  survived.value = 0
  diamondsAwarded.value = null
  saveError.value = ''
  finishedPosted = false
  acc = 0
}

function clampPlayer(): void {
  player.x = Math.max(0, Math.min(WIDTH - SPRITE, player.x))
  player.y = Math.max(0, Math.min(HEIGHT - SPRITE, player.y))
}

function step(): void {
  if (keys.has('KeyD')) player.x += 5
  if (keys.has('KeyA')) player.x -= 5
  if (keys.has('KeyS')) player.y += 5
  if (keys.has('KeyW')) player.y -= 5
  clampPlayer()
  let lostHeart = false
  for (const p of pumpkins) {
    const prevY = p.y
    p.y += p.speed
    p.speed += 0.0005
    const crossed =
      p.x < player.x + SPRITE &&
      p.x + SPRITE > player.x &&
      prevY < player.y + SPRITE &&
      p.y + SPRITE > player.y
    if (crossed) {
      resetPumpkin(p)
      lostHeart = true
    } else if (p.y > HEIGHT) {
      resetPumpkin(p)
    }
  }
  if (lostHeart) hearts -= 1
  simMs += STEP_MS
  seconds.value = Math.floor(simMs / 1000)
  if (hearts <= 0) {
    hearts = 0
    void endRun()
  }
}

async function endRun(): Promise<void> {
  if (mode.value !== 'game') return
  const token = runToken
  survived.value = seconds.value
  mode.value = 'gameover'
  stopLoop()
  draw()
  if (finishedPosted) return
  finishedPosted = true
  const pending = startPromise
  const started = pending ? await pending : false
  if (token !== runToken || mode.value !== 'gameover') return
  if (!started) {
    saveError.value = t('pumpkinDodge.saveError')
    draw()
    return
  }
  try {
    const data = await apiPost<{ diamonds_awarded: number; diamonds: number }>(
      '/pumpkin-dodge/finish',
      { seconds: survived.value },
      auth.token,
    )
    try {
      await auth.refreshProfile()
    } catch {
      auth.mergeOtherData({ diamonds: data.diamonds })
    }
    if (token !== runToken || mode.value !== 'gameover') return
    diamondsAwarded.value = data.diamonds_awarded
  } catch {
    if (token !== runToken || mode.value !== 'gameover') return
    saveError.value = t('pumpkinDodge.saveError')
  }
  draw()
}

function stopLoop(): void {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
}

function loop(now: number): void {
  if (mode.value !== 'game') return
  const dt = Math.min(100, now - lastTs)
  lastTs = now
  acc += dt
  while (acc >= STEP_MS && mode.value === 'game') {
    step()
    acc -= STEP_MS
  }
  draw()
  if (mode.value === 'game') raf = requestAnimationFrame(loop)
}

async function startGame(): Promise<void> {
  if (starting || mode.value === 'game') return
  starting = true
  resetRun()
  mode.value = 'game'
  stopLoop()
  draw()
  ensureMusic()
  try {
    startPromise = apiPost('/pumpkin-dodge/start', {}, auth.token).then(() => true).catch(() => false)
    lastTs = performance.now()
    raf = requestAnimationFrame(loop)
    await startPromise
  } finally {
    starting = false
  }
}

async function openTop(): Promise<void> {
  mode.value = 'top'
  stopLoop()
  topLoading.value = true
  draw()
  try {
    const data = await apiGet<{ users: typeof topUsers.value }>(
      `/leaderboard?limit=10&game=${GAME_KEY}`,
      auth.token,
    )
    topUsers.value = data.users
  } catch {
    topUsers.value = []
  } finally {
    topLoading.value = false
  }
}

function goMenu(): void {
  mode.value = 'menu'
  stopLoop()
  draw()
}

function exitGame(): void {
  router.push('/games')
}

function ctx(): CanvasRenderingContext2D | null {
  const canvas = canvasRef.value
  if (!canvas) return null
  return canvas.getContext('2d')
}

function drawImage(context: CanvasRenderingContext2D, name: string, x: number, y: number, w: number, h: number): void {
  const img = images[name]
  if (img) context.drawImage(img, x, y, w, h)
}

function draw(): void {
  const context = ctx()
  if (!context) return
  context.clearRect(0, 0, WIDTH, HEIGHT)
  if (mode.value === 'menu') {
    drawImage(context, 'menu_background', 0, 0, WIDTH, HEIGHT)
    return
  }
  if (mode.value === 'top') {
    drawImage(context, 'top_players_background', 0, 0, WIDTH, HEIGHT)
    drawImage(context, 'back_button', BACK_BTN.x, BACK_BTN.y, BACK_BTN.w, BACK_BTN.h)
    return
  }
  if (mode.value === 'game') {
    drawImage(context, 'game_background', 0, 0, WIDTH, HEIGHT)
    for (const p of pumpkins) drawImage(context, 'pumpkin', p.x, p.y, SPRITE, SPRITE)
    drawImage(context, 'player', player.x, player.y, SPRITE, SPRITE)
    for (let i = 0; i < hearts; i += 1) drawImage(context, 'heart', 850 + i * 50, 10, 40, 40)
    context.fillStyle = '#fff'
    context.font = '28px sans-serif'
    context.textAlign = 'right'
    context.fillText(t('pumpkinDodge.timer', { seconds: seconds.value }), WIDTH - 20, HEIGHT - 24)
    drawImage(context, 'back_button', BACK_BTN.x, BACK_BTN.y, BACK_BTN.w, BACK_BTN.h)
    return
  }
  context.fillStyle = '#c80000'
  context.fillRect(0, 0, WIDTH, HEIGHT)
  context.fillStyle = '#fff'
  context.font = '36px sans-serif'
  context.textAlign = 'center'
  context.fillText(t('pumpkinDodge.survived', { seconds: survived.value }), WIDTH / 2, 250)
  if (diamondsAwarded.value !== null) {
    context.font = '28px sans-serif'
    context.fillText(t('pumpkinDodge.reward', { count: diamondsAwarded.value }), WIDTH / 2, 310)
  }
  if (saveError.value) {
    context.font = '22px sans-serif'
    context.fillText(saveError.value, WIDTH / 2, 360)
  }
  drawImage(context, 'back_button', BACK_BTN.x, BACK_BTN.y, BACK_BTN.w, BACK_BTN.h)
}

function logicalPoint(event: PointerEvent): { x: number; y: number } | null {
  const canvas = canvasRef.value
  if (!canvas) return null
  const box = canvas.getBoundingClientRect()
  if (!box.width || !box.height) return null
  return {
    x: ((event.clientX - box.left) / box.width) * WIDTH,
    y: ((event.clientY - box.top) / box.height) * HEIGHT,
  }
}

function pumpkinAt(x: number, y: number): Pumpkin | null {
  for (let i = pumpkins.length - 1; i >= 0; i -= 1) {
    const p = pumpkins[i]
    if (x >= p.x && x <= p.x + SPRITE && y >= p.y && y <= p.y + SPRITE) return p
  }
  return null
}

function onPointerDown(event: PointerEvent): void {
  const point = logicalPoint(event)
  if (!point) return
  ensureMusic()
  if (mode.value === 'menu') {
    if (hit(START_BTN, point.x, point.y)) startGame()
    else if (hit(TOP_BTN, point.x, point.y)) void openTop()
    else if (hit(EXIT_BTN, point.x, point.y)) exitGame()
    return
  }
  if (hit(BACK_BTN, point.x, point.y) && mode.value !== 'menu') {
    goMenu()
    return
  }
  if (mode.value === 'game') {
    if (hit(SECRET_BTN, point.x, point.y) && hearts < 3) {
      hearts += 1
      draw()
      return
    }
    const pumpkin = pumpkinAt(point.x, point.y)
    if (pumpkin) {
      resetPumpkin(pumpkin)
      draw()
    }
  }
}

function onKeyDown(event: KeyboardEvent): void {
  keys.add(event.code)
}

function onKeyUp(event: KeyboardEvent): void {
  keys.delete(event.code)
}

function onBlur(): void {
  keys.clear()
}

function ensureMusic(): void {
  if (!music) {
    const index = 1 + Math.floor(Math.random() * 6)
    music = new Audio(`${ASSET}/music/main_theme${index}.mp3`)
    music.loop = true
    music.volume = 0.1
  }
  void music.play().catch(() => {})
}

function rowScore(user: { other_data?: { games?: Record<string, { high_score_seconds?: number }> } }): number {
  return Number(user.other_data?.games?.[GAME_KEY]?.high_score_seconds ?? 0)
}

function medal(index: number): string {
  if (index === 0) return '🥇'
  if (index === 1) return '🥈'
  if (index === 2) return '🥉'
  return String(index + 1)
}

const showTopList = computed(() => mode.value === 'top')

function resizeCanvas(): void {
  const canvas = canvasRef.value
  const stage = stageRef.value
  if (!canvas || !stage) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.floor(WIDTH * dpr)
  canvas.height = Math.floor(HEIGHT * dpr)
  const context = canvas.getContext('2d')
  context?.setTransform(dpr, 0, 0, dpr, 0, 0)
  draw()
}

onMounted(async () => {
  startPresencePing(auth.token, GAME_KEY)
  await Promise.all(
    ['menu_background', 'game_background', 'top_players_background', 'player', 'pumpkin', 'heart', 'back_button'].map(loadImage),
  )
  resizeCanvas()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('blur', onBlur)
  window.addEventListener('resize', resizeCanvas)
  ensureMusic()
})

onBeforeUnmount(() => {
  stopLoop()
  stopPresencePing()
  if (music) {
    music.pause()
    music.src = ''
    music = null
  }
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('blur', onBlur)
  window.removeEventListener('resize', resizeCanvas)
})
</script>

<template>
  <main class="pd-page">
    <div ref="stageRef" class="pd-stage">
      <canvas
        ref="canvasRef"
        class="pd-canvas"
        @pointerdown="onPointerDown"
      />
      <div v-if="showTopList" class="pd-top">
        <p v-if="topLoading" class="pd-top-empty">{{ t('common.loading') }}</p>
        <p v-else-if="!topUsers.length" class="pd-top-empty">{{ t('pumpkinDodge.empty') }}</p>
        <ol v-else class="pd-top-list">
          <li
            v-for="(user, index) in topUsers"
            :key="user.username"
            :class="{ 'pd-top-me': user.username === auth.username }"
          >
            <span>{{ medal(index) }}</span>
            <span class="pd-top-name">{{ user.username }}</span>
            <span class="pd-top-score">{{ rowScore(user) }}</span>
          </li>
        </ol>
      </div>
    </div>
    <p class="pd-help">{{ t('pumpkinDodge.controls') }}</p>
  </main>
</template>

<style scoped>
.pd-page {
  min-height: 100vh;
  background: #111;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px;
}
.pd-stage {
  position: relative;
  width: min(1000px, 100%);
  aspect-ratio: 1000 / 600;
}
.pd-canvas {
  width: 100%;
  height: 100%;
  display: block;
  touch-action: none;
  border-radius: 8px;
}
.pd-top {
  position: absolute;
  left: 18%;
  top: 36%;
  width: 64%;
  height: 42%;
  overflow: auto;
  color: #1c140c;
  pointer-events: auto;
}
.pd-top-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
}
.pd-top-list li {
  display: grid;
  grid-template-columns: 42px 1fr auto;
  gap: 8px;
  align-items: center;
  font-weight: 800;
  font-size: clamp(14px, 2vw, 22px);
}
.pd-top-me {
  background: rgba(255, 214, 120, 0.45);
  border-radius: 8px;
}
.pd-top-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pd-top-score {
  font-variant-numeric: tabular-nums;
}
.pd-top-empty {
  margin: 0;
  text-align: center;
  font-weight: 800;
  font-size: 20px;
}
.pd-help {
  margin: 0;
  color: rgba(255, 255, 255, 0.78);
  font-size: 13px;
  text-align: center;
}
</style>
