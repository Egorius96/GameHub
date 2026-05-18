<script setup lang="ts">
import { ref, watch } from 'vue'
import { playSfx } from '../../audio/sound'

const props = defineProps<{
  show: boolean
  won: boolean
  tie?: boolean
  playerScore: number
  opponentScore: number
  opponentLabel?: string
  rewardPending?: boolean
}>()

const emit = defineEmits<{
  restart: []
  exit: []
}>()

const entered = ref(false)

watch(
  () => props.show,
  (v) => {
    if (v) {
      entered.value = false
      window.requestAnimationFrame(() => {
        entered.value = true
      })
      playSfx(props.tie ? 'button' : props.won ? 'diamond' : 'button')
    } else {
      entered.value = false
    }
  },
  { immediate: true }
)

function onRestart() {
  playSfx('button')
  emit('restart')
}

function onExit() {
  playSfx('button')
  emit('exit')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="rps-end-fade">
      <div v-if="show" class="rps-end-overlay" role="dialog" aria-modal="true" aria-labelledby="rps-end-title">
        <div class="rps-end-backdrop" @click="onExit" />
        <div
          class="rps-end-card"
          :class="{
            'rps-end-card--win': won && !tie,
            'rps-end-card--lose': !won && !tie,
            'rps-end-card--tie': tie,
            'rps-end-card--in': entered,
          }"
        >
          <div class="rps-end-glow" aria-hidden="true" />
          <p class="rps-end-eyebrow">Итог матча (3 раунда)</p>
          <h2
            id="rps-end-title"
            class="rps-end-title"
            :class="tie ? 'rps-end-title--tie' : won ? 'rps-end-title--win' : 'rps-end-title--lose'"
          >
            {{ tie ? 'Ничья!' : won ? 'Победа!' : 'Проигрыш' }}
          </h2>
          <p class="rps-end-score">
            Вы <strong>{{ playerScore }}</strong>
            <span class="rps-end-score-sep">:</span>
            <strong>{{ opponentScore }}</strong>
            {{ opponentLabel || 'соперник' }}
          </p>
          <p v-if="tie" class="rps-end-hint">Равный счёт побед — матч завершён вничью.</p>
          <p v-else-if="won && rewardPending" class="rps-end-hint">Алмаз скоро появится в копилке…</p>
          <p v-else-if="won" class="rps-end-hint">+1 алмаз в копилку GameHub</p>
          <p v-else class="rps-end-hint">В следующий раз повезёт!</p>
          <div class="rps-end-actions">
            <button type="button" class="btn rps-end-btn rps-end-btn--primary" @click="onRestart">Начать заново</button>
            <button type="button" class="btn rps-end-btn rps-end-btn--ghost" @click="onExit">Закончить игру</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.rps-end-overlay {
  position: fixed;
  inset: 0;
  z-index: 10050;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.rps-end-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(4, 8, 18, 0.72);
  backdrop-filter: blur(8px);
}
.rps-end-card {
  position: relative;
  z-index: 1;
  pointer-events: auto;
  width: min(400px, 100%);
  padding: 28px 24px 24px;
  border-radius: 24px;
  text-align: center;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: linear-gradient(165deg, rgba(22, 32, 58, 0.97), rgba(10, 14, 28, 0.98));
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.55);
  transform: scale(0.88) translateY(16px);
  opacity: 0;
  transition:
    transform 0.45s cubic-bezier(0.34, 1.35, 0.64, 1),
    opacity 0.35s ease;
  overflow: hidden;
}
.rps-end-card--in {
  transform: scale(1) translateY(0);
  opacity: 1;
}
.rps-end-card--win {
  border-color: rgba(129, 199, 132, 0.45);
}
.rps-end-card--lose {
  border-color: rgba(239, 83, 80, 0.4);
}
.rps-end-card--tie {
  border-color: rgba(144, 202, 249, 0.45);
}
.rps-end-card--tie .rps-end-glow {
  background: radial-gradient(ellipse, rgba(100, 181, 246, 0.45), transparent 70%);
}
.rps-end-title--tie {
  background: linear-gradient(135deg, #90caf9, #42a5f5, #e3f2fd);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.rps-end-glow {
  position: absolute;
  top: -40%;
  left: 50%;
  width: 120%;
  height: 80%;
  transform: translateX(-50%);
  pointer-events: none;
  opacity: 0.35;
}
.rps-end-card--win .rps-end-glow {
  background: radial-gradient(ellipse, rgba(102, 187, 106, 0.55), transparent 70%);
}
.rps-end-card--lose .rps-end-glow {
  background: radial-gradient(ellipse, rgba(229, 57, 53, 0.4), transparent 70%);
}
.rps-end-eyebrow {
  margin: 0 0 8px;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  opacity: 0.65;
}
.rps-end-title {
  margin: 0 0 12px;
  font-size: clamp(2rem, 8vw, 2.6rem);
  font-weight: 900;
  letter-spacing: 0.04em;
}
.rps-end-title--win {
  background: linear-gradient(135deg, #a5d6a7, #69f0ae, #e8f5e9);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 0 24px rgba(105, 240, 174, 0.45));
}
.rps-end-title--lose {
  background: linear-gradient(135deg, #ef9a9a, #ff5252, #ffcdd2);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 0 20px rgba(255, 82, 82, 0.35));
}
.rps-end-score {
  margin: 0 0 10px;
  font-size: 1.05rem;
  opacity: 0.92;
}
.rps-end-score-sep {
  margin: 0 6px;
  opacity: 0.5;
}
.rps-end-hint {
  margin: 0 0 22px;
  font-size: 0.92rem;
  opacity: 0.78;
}
.rps-end-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rps-end-btn {
  width: 100%;
  min-height: 48px;
  font-size: 1rem;
  border-radius: 14px;
}
.rps-end-btn--primary {
  background: linear-gradient(180deg, #5c8aff, #3d5fc4);
  border-color: rgba(140, 180, 255, 0.5);
}
.rps-end-btn--ghost {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.18);
}
.rps-end-fade-enter-active,
.rps-end-fade-leave-active {
  transition: opacity 0.3s ease;
}
.rps-end-fade-enter-from,
.rps-end-fade-leave-to {
  opacity: 0;
}
</style>
