<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { playProRacingSfx, startGameMusic, stopMusic } from '../../audio/sound'
import { startHeartbeat, stopHeartbeat } from '../../telemetry/heartbeat'
import { startPresencePing, stopPresencePing } from '../../telemetry/presence'

const router = useRouter()
const auth = useAuthStore()

const diamonds = computed(() => Number((auth.otherData as any).diamonds ?? 0))
const gameData = computed(() => ((auth.otherData as any).games ?? {})?.misha_pro_racing_game ?? {})
const level = computed(() => Number((gameData.value as any).car_level ?? 1))

onMounted(async () => {
  await auth.refreshProfile()
  startGameMusic()
  startHeartbeat(auth.token, 'misha_pro_racing_game')
  startPresencePing(auth.token, 'misha_pro_racing_game')
})

onBeforeUnmount(() => {
  stopHeartbeat()
  stopPresencePing()
})

onBeforeRouteLeave((to) => {
  if (to.path === '/games') stopMusic()
})

function openMode(m: string) {
  playProRacingSfx('button')
  router.push(`/game/${m}`)
}

function go(path: string) {
  playProRacingSfx('button')
  router.push(path)
}
</script>

<template>
  <main class="page pr-page">
    <div class="pr-bg" aria-hidden="true" />
    <section class="pr-shell">
      <header class="pr-hero">
        <p class="pr-kicker">Pro Racing</p>
        <h1 class="pr-title">Главное меню</h1>
        <p class="pr-sub">Привет, <strong>{{ auth.username }}</strong></p>
        <div class="pr-stats">
          <div class="pr-stat">
            <span class="pr-stat-label">Алмазы</span>
            <span class="pr-stat-value">{{ diamonds }}</span>
          </div>
          <div class="pr-stat">
            <span class="pr-stat-label">Уровень машины</span>
            <span class="pr-stat-value">{{ level }} / 3</span>
          </div>
        </div>
      </header>

      <h2 class="pr-section-title">Режим</h2>
      <div class="pr-mode-grid">
        <button type="button" class="pr-mode-card pr-mode-card--accent" @click="openMode('normal')">
          <span class="pr-mode-icon" aria-hidden="true">▶</span>
          <span class="pr-mode-name">Обычный</span>
          <span class="pr-mode-desc">Классический заезд, WASD</span>
        </button>
        <button type="button" class="pr-mode-card" @click="openMode('hard')">
          <span class="pr-mode-icon" aria-hidden="true">⚡</span>
          <span class="pr-mode-name">Сложный</span>
          <span class="pr-mode-desc">Быстрее и жёстче модификаторы</span>
        </button>
        <button
          type="button"
          class="pr-mode-card"
          :class="{ 'pr-mode-card--locked': level < 3 }"
          :disabled="level < 3"
          @click="openMode('pvp_local')"
        >
          <span class="pr-mode-icon" aria-hidden="true">👥</span>
          <span class="pr-mode-name">Два игрока</span>
          <span class="pr-mode-desc">
            {{ level < 3 ? `Нужен уровень машины 3 (сейчас ${level})` : 'Стрелки — второй игрок' }}
          </span>
        </button>
      </div>

      <h2 class="pr-section-title">Ещё</h2>
      <div class="pr-actions">
        <button type="button" class="pr-link-btn" @click="go('/store')">Магазин и настройки</button>
        <button type="button" class="pr-link-btn" @click="go('/leaderboard')">Таблица лидеров</button>
        <button type="button" class="pr-link-btn pr-link-btn--ghost" @click="go('/games')">Выйти в хаб</button>
      </div>
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
    radial-gradient(ellipse 120% 80% at 50% -20%, rgba(100, 140, 255, 0.35), transparent 55%),
    radial-gradient(ellipse 80% 50% at 100% 100%, rgba(255, 120, 80, 0.12), transparent 45%),
    linear-gradient(165deg, #0a0e1a 0%, #121a2e 50%, #0c1020 100%);
  z-index: 0;
  pointer-events: none;
}
.pr-shell {
  position: relative;
  z-index: 1;
  max-width: 520px;
  margin: 0 auto;
  padding: 28px 20px 40px;
}
.pr-hero {
  margin-bottom: 28px;
}
.pr-kicker {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(140, 180, 255, 0.9);
}
.pr-title {
  margin: 0 0 8px;
  font-size: clamp(1.6rem, 4vw, 2rem);
  font-weight: 800;
  letter-spacing: -0.02em;
}
.pr-sub {
  margin: 0 0 20px;
  font-size: 15px;
  opacity: 0.88;
}
.pr-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.pr-stat {
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pr-stat-label {
  font-size: 12px;
  opacity: 0.72;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.pr-stat-value {
  font-size: 1.35rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.pr-section-title {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.65;
}
.pr-mode-grid {
  display: grid;
  gap: 12px;
  margin-bottom: 28px;
}
.pr-mode-card {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 14px;
  row-gap: 4px;
  padding: 16px 18px;
  text-align: left;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(12, 18, 36, 0.72);
  color: inherit;
  font: inherit;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.pr-mode-card:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: rgba(130, 170, 255, 0.35);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}
.pr-mode-card:active:not(:disabled) {
  transform: translateY(0);
}
.pr-mode-card--accent {
  border-color: rgba(100, 200, 160, 0.45);
  background: linear-gradient(145deg, rgba(30, 70, 55, 0.55), rgba(12, 18, 36, 0.85));
}
.pr-mode-card--locked {
  opacity: 0.55;
  cursor: not-allowed;
}
.pr-mode-icon {
  grid-row: 1 / span 2;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  font-size: 1.1rem;
}
.pr-mode-name {
  font-weight: 800;
  font-size: 1.05rem;
}
.pr-mode-desc {
  grid-column: 2;
  font-size: 13px;
  opacity: 0.78;
  line-height: 1.35;
}
.pr-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pr-link-btn {
  padding: 14px 18px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  font: inherit;
  font-weight: 600;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.pr-link-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(140, 170, 255, 0.35);
}
.pr-link-btn--ghost {
  opacity: 0.85;
  background: transparent;
}
</style>
