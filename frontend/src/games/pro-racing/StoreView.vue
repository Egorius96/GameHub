<script setup lang="ts">
import { computed, onBeforeUnmount, ref, TransitionGroup } from 'vue'
import { useRouter } from 'vue-router'
import { apiPost, ApiHttpError } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { playProRacingSfx, stopGameMusicOnly } from '../../audio/sound'
import { proRacingMusicEnabled, proRacingSfxEnabled } from './audioSettings'

/** Как backend/app/api/store.py CARS_COSTS */
const CARS_COSTS: Record<number, number> = { 1: 0, 2: 20, 3: 100 }

const auth = useAuthStore()
const router = useRouter()

const carLevel = computed(() =>
  Number((auth.otherData as any)?.games?.misha_pro_racing_game?.car_level ?? 1),
)

const nextUpgradeCost = computed(() => {
  const lv = carLevel.value
  if (lv >= 3) return null
  return CARS_COSTS[lv + 1] ?? null
})

type ToastItem = { id: number; text: string; variant: 'warn' | 'ok' }
const toasts = ref<ToastItem[]>([])
let toastSeq = 0
const toastTimers = new Map<number, ReturnType<typeof setTimeout>>()

function pushToast(text: string, variant: ToastItem['variant'] = 'warn') {
  const id = ++toastSeq
  toasts.value = [...toasts.value, { id, text, variant }]
  const t = setTimeout(() => dismissToast(id), 4500)
  toastTimers.set(id, t)
}

function dismissToast(id: number) {
  const t = toastTimers.get(id)
  if (t) clearTimeout(t)
  toastTimers.delete(id)
  toasts.value = toasts.value.filter((x) => x.id !== id)
}

onBeforeUnmount(() => {
  toastTimers.forEach((t) => clearTimeout(t))
  toastTimers.clear()
})

function apiErrorText(e: unknown): string {
  if (e instanceof ApiHttpError) {
    const m = e.message
    const need = /^Need (\d+) diamonds$/i.exec(m)
    if (need) return `Не хватает ${need[1]} алмазов`
    if (/Max car level/i.test(m)) return 'Машина максимального уровня'
    if (/Already purchased/i.test(m)) return 'Уже куплено'
    return m
  }
  return 'Ошибка запроса'
}

function onMusicToggle() {
  if (!proRacingMusicEnabled.value) stopGameMusicOnly()
}

async function upgradeCar() {
  if (carLevel.value >= 3) {
    pushToast('Машина максимального уровня', 'warn')
    return
  }
  try {
    playProRacingSfx('purchase')
    const data = await apiPost<{ car_level: number; diamonds: number }>('/store/upgrade-car', {}, auth.token)
    ;(auth.otherData as any).games = (auth.otherData as any).games ?? {}
    ;(auth.otherData as any).games.misha_pro_racing_game = (auth.otherData as any).games.misha_pro_racing_game ?? {}
    ;(auth.otherData as any).games.misha_pro_racing_game.car_level = data.car_level
    ;(auth.otherData as any).diamonds = data.diamonds
    pushToast('Машина улучшена', 'ok')
  } catch (e) {
    pushToast(apiErrorText(e), 'warn')
  }
}

async function buy(superpower: string) {
  try {
    playProRacingSfx('purchase')
    const data = await apiPost<{ diamonds: number; superpowers: Record<string, boolean> }>(
      '/store/buy-superpower',
      { superpower },
      auth.token,
    )
    ;(auth.otherData as any).diamonds = data.diamonds
    ;(auth.otherData as any).games = (auth.otherData as any).games ?? {}
    ;(auth.otherData as any).games.misha_pro_racing_game = (auth.otherData as any).games.misha_pro_racing_game ?? {}
    ;(auth.otherData as any).games.misha_pro_racing_game.superpowers = data.superpowers
    pushToast(`Куплено: ${labelSp(superpower)}`, 'ok')
  } catch (e) {
    pushToast(apiErrorText(e), 'warn')
  }
}

function labelSp(key: string): string {
  const m: Record<string, string> = {
    drugs: 'Drugs',
    immue: 'Immue',
    rockspeed: 'Rockspeed',
    hearty_rock: 'Hearty rock',
  }
  return m[key] ?? key
}

function back() {
  playProRacingSfx('button')
  router.push('/menu')
}
</script>

<template>
  <main class="page pr-page">
    <div class="pr-bg" aria-hidden="true" />
    <section class="pr-shell">
      <header class="pr-head">
        <p class="pr-kicker">Pro Racing</p>
        <h1 class="pr-title">Магазин</h1>
        <p class="pr-balance">
          <img src="/assets/original/brilliant.png" alt="" class="pr-diamond-ico" width="28" height="18" />
          <span>{{ (auth.otherData as any).diamonds ?? 0 }}</span>
          <span class="pr-balance-hint">алмазов</span>
        </p>
      </header>

      <div class="pr-card">
        <h2 class="pr-card-title">Звук</h2>
        <label class="pr-toggle">
          <input v-model="proRacingMusicEnabled" type="checkbox" class="pr-toggle-input" @change="onMusicToggle" />
          <span class="pr-toggle-ui" />
          <span class="pr-toggle-text">Музыка в игре</span>
        </label>
        <label class="pr-toggle">
          <input v-model="proRacingSfxEnabled" type="checkbox" class="pr-toggle-input" />
          <span class="pr-toggle-ui" />
          <span class="pr-toggle-text">Звуковые эффекты</span>
        </label>
      </div>

      <div class="pr-card">
        <h2 class="pr-card-title">Машина</h2>
        <p class="pr-car-level">Уровень: {{ carLevel }} / 3</p>
        <button
          type="button"
          class="pr-primary"
          :disabled="carLevel >= 3"
          @click="upgradeCar"
        >
          <template v-if="carLevel >= 3">Максимальный уровень</template>
          <template v-else>Улучшить за {{ nextUpgradeCost }} алм.</template>
        </button>
        <p class="pr-hint">
          Повышает уровень кузова (визуал в игре).
          <template v-if="carLevel < 3"> Стоимость следующего шага: {{ nextUpgradeCost }} алмазов.</template>
        </p>
      </div>

      <h2 class="pr-section-title">Суперспособности</h2>
      <div class="pr-shop-grid">
        <div class="pr-offer">
          <div class="pr-offer-top">
            <span class="pr-offer-name">Drugs</span>
            <span class="pr-offer-price">50 алм.</span>
          </div>
          <p class="pr-offer-desc">Временный буст</p>
          <button type="button" class="pr-buy" @click="buy('drugs')">Купить</button>
        </div>
        <div class="pr-offer">
          <div class="pr-offer-top">
            <span class="pr-offer-name">Immue</span>
            <span class="pr-offer-price">200 алм.</span>
          </div>
          <p class="pr-offer-desc">Короткая неуязвимость</p>
          <button type="button" class="pr-buy" @click="buy('immue')">Купить</button>
        </div>
        <div class="pr-offer">
          <div class="pr-offer-top">
            <span class="pr-offer-name">Rockspeed</span>
            <span class="pr-offer-price">300 алм.</span>
          </div>
          <p class="pr-offer-desc">Замедление камней</p>
          <button type="button" class="pr-buy" @click="buy('rockspeed')">Купить</button>
        </div>
        <div class="pr-offer">
          <div class="pr-offer-top">
            <span class="pr-offer-name">Hearty rock</span>
            <span class="pr-offer-price">100 алм.</span>
          </div>
          <p class="pr-offer-desc">Спасение от удара</p>
          <button type="button" class="pr-buy" @click="buy('hearty_rock')">Купить</button>
        </div>
      </div>

      <button type="button" class="pr-back" @click="back">← В меню</button>

      <Teleport to="body">
        <div class="pr-notify-stack" aria-live="polite">
          <TransitionGroup name="pr-notify">
            <div
              v-for="t in toasts"
              :key="t.id"
              :class="['pr-notify', t.variant === 'warn' ? 'pr-notify--warn' : 'pr-notify--ok']"
            >
              <span class="pr-notify-text">{{ t.text }}</span>
              <button type="button" class="pr-notify-close" aria-label="Закрыть" @click="dismissToast(t.id)">×</button>
            </div>
          </TransitionGroup>
        </div>
      </Teleport>
    </section>
  </main>
</template>

<style scoped>
.pr-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
}
.pr-bg {
  position: fixed;
  inset: 0;
  background:
    radial-gradient(ellipse 100% 70% at 20% 0%, rgba(120, 90, 255, 0.2), transparent 50%),
    linear-gradient(165deg, #0a0e1a 0%, #121a2e 55%, #0c1020 100%);
  z-index: 0;
  pointer-events: none;
}
.pr-shell {
  position: relative;
  z-index: 1;
  max-width: 560px;
  margin: 0 auto;
  padding: 24px 18px 36px;
}
.pr-kicker {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(160, 190, 255, 0.85);
}
.pr-title {
  margin: 0 0 12px;
  font-size: 1.65rem;
  font-weight: 800;
}
.pr-balance {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 1.35rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.pr-diamond-ico {
  object-fit: contain;
}
.pr-balance-hint {
  font-size: 14px;
  font-weight: 500;
  opacity: 0.65;
}
.pr-card {
  margin-top: 18px;
  padding: 18px;
  border-radius: 16px;
  background: rgba(12, 18, 36, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.pr-card-title {
  margin: 0 0 14px;
  font-size: 14px;
  font-weight: 700;
}
.pr-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  user-select: none;
}
.pr-toggle:last-of-type {
  margin-bottom: 0;
}
.pr-toggle-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.pr-toggle-ui {
  width: 48px;
  height: 28px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.18);
  flex-shrink: 0;
  position: relative;
  transition: background 0.2s ease;
}
.pr-toggle-ui::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s ease;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
}
.pr-toggle-input:checked + .pr-toggle-ui {
  background: linear-gradient(90deg, #4a7cff, #6a9fff);
  border-color: rgba(120, 170, 255, 0.5);
}
.pr-toggle-input:checked + .pr-toggle-ui::after {
  transform: translateX(20px);
}
.pr-toggle-text {
  font-size: 15px;
  font-weight: 600;
}
.pr-primary {
  width: 100%;
  padding: 14px 18px;
  border-radius: 14px;
  border: none;
  font: inherit;
  font-weight: 700;
  font-size: 15px;
  cursor: pointer;
  color: #0a1020;
  background: linear-gradient(180deg, #8ae8c0, #3da67a);
  box-shadow: 0 8px 24px rgba(40, 160, 120, 0.35);
}
.pr-primary:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  filter: grayscale(0.25);
  box-shadow: none;
}
.pr-primary:hover:not(:disabled) {
  filter: brightness(1.06);
}
.pr-car-level {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  opacity: 0.85;
}
.pr-hint {
  margin: 10px 0 0;
  font-size: 13px;
  opacity: 0.72;
  line-height: 1.4;
}
.pr-section-title {
  margin: 26px 0 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  opacity: 0.6;
}
.pr-shop-grid {
  display: grid;
  gap: 12px;
}
@media (min-width: 520px) {
  .pr-shop-grid {
    grid-template-columns: 1fr 1fr;
  }
}
.pr-offer {
  padding: 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pr-offer-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.pr-offer-name {
  font-weight: 800;
  font-size: 1rem;
}
.pr-offer-price {
  font-size: 14px;
  font-weight: 700;
  color: rgba(200, 230, 255, 0.95);
  white-space: nowrap;
}
.pr-offer-desc {
  margin: 0;
  font-size: 13px;
  opacity: 0.75;
  flex: 1;
}
.pr-buy {
  margin-top: 4px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(140, 170, 255, 0.35);
  background: rgba(70, 110, 220, 0.25);
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.pr-buy:hover {
  background: rgba(90, 130, 240, 0.38);
}
.pr-notify-stack {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 10050;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: min(360px, calc(100vw - 32px));
  pointer-events: none;
}
.pr-notify {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.12);
  pointer-events: auto;
}
.pr-notify--warn {
  background: linear-gradient(145deg, rgba(140, 82, 42, 0.94), rgba(95, 52, 28, 0.96));
  color: rgba(255, 245, 230, 0.96);
  border-color: rgba(255, 180, 120, 0.22);
}
.pr-notify--ok {
  background: linear-gradient(145deg, rgba(42, 88, 72, 0.92), rgba(24, 52, 44, 0.95));
  color: rgba(220, 255, 238, 0.95);
  border-color: rgba(120, 220, 170, 0.2);
}
.pr-notify-text {
  flex: 1;
  min-width: 0;
}
.pr-notify-close {
  flex-shrink: 0;
  margin: -4px -6px -4px 0;
  padding: 4px 8px;
  border: none;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
  color: inherit;
  font: inherit;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  opacity: 0.85;
}
.pr-notify-close:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.28);
}
.pr-notify-enter-active,
.pr-notify-leave-active {
  transition: all 0.28s ease;
}
.pr-notify-enter-from {
  opacity: 0;
  transform: translateX(12px);
}
.pr-notify-leave-to {
  opacity: 0;
  transform: translateX(8px);
}
.pr-notify-move {
  transition: transform 0.28s ease;
}
.pr-back {
  margin-top: 22px;
  width: 100%;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.pr-back:hover {
  border-color: rgba(140, 170, 255, 0.35);
}
</style>
