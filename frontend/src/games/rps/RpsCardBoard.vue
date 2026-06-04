<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { GAME_ASSETS_BASE } from '../../config/gameAssets'
const { t } = useI18n()


export type RpsMove = 'rock' | 'paper' | 'scissors'
export type RpsRoundVerdict = 'win' | 'lose' | 'tie' | null

const props = withDefaults(
  defineProps<{
    selected?: RpsMove | null
    opponentRevealed?: boolean
    opponentMoves?: Partial<Record<RpsMove, RpsMove | null>>
    disabled?: boolean
    highlightWinner?: 'player' | 'opponent' | 'tie' | null
    roundVerdict?: RpsRoundVerdict
    playerMoves?: RpsMove[]
    opponentMovesOrder?: RpsMove[]
  }>(),
  {
    selected: null,
    opponentRevealed: false,
    opponentMoves: () => ({}),
    disabled: false,
    highlightWinner: null,
    roundVerdict: null,
    playerMoves: () => ['rock', 'scissors', 'paper'],
    opponentMovesOrder: () => ['rock', 'scissors', 'paper'],
  }
)

const emit = defineEmits<{
  pick: [move: RpsMove]
}>()

const labels: Record<RpsMove, string> = {
  rock: t('rps.moves.rock'),
  paper: t('rps.moves.paper'),
  scissors: t('rps.moves.scissors'),
}

const faces: Record<RpsMove, string> = {
  rock: `${GAME_ASSETS_BASE}/rps/rock.png`,
  paper: `${GAME_ASSETS_BASE}/rps/paper.png`,
  scissors: `${GAME_ASSETS_BASE}/rps/scissors.png`,
}

const backSrc = `${GAME_ASSETS_BASE}/rps/back_side.png`

function onPick(move: RpsMove) {
  if (props.disabled) return
  emit('pick', move)
}

function oppFace(move: RpsMove): string {
  const m = props.opponentMoves?.[move]
  if (props.opponentRevealed && m) return faces[m]
  return backSrc
}

function isFlippedOpp(move: RpsMove): boolean {
  return props.opponentRevealed && Boolean(props.opponentMoves?.[move])
}

function playerWinClass(move: RpsMove): string {
  if (props.highlightWinner !== 'player' || props.selected !== move) return ''
  return 'rps-card--win'
}

function oppWinClass(move: RpsMove): boolean {
  if (props.highlightWinner !== 'opponent') return false
  const m = props.opponentMoves?.[move]
  return Boolean(m && props.opponentRevealed)
}

const showPickMark = computed(() => Boolean(props.selected) && !props.opponentRevealed)
</script>

<template>
  <div class="rps-board">
    <p class="rps-board-label">{{ t('rps.opponent') }}</p>
    <div class="rps-card-row">
      <button
        v-for="slot in opponentMovesOrder"
        :key="'opp-' + slot"
        type="button"
        class="rps-card rps-card--opp"
        :class="{
          'rps-card--flipped': isFlippedOpp(slot),
          'rps-card--win': oppWinClass(slot),
        }"
        disabled
        tabindex="-1"
      >
        <span class="rps-card-inner">
          <img class="rps-card-face rps-card-face--back" :src="backSrc" alt="" />
          <img class="rps-card-face rps-card-face--front" :src="oppFace(slot)" :alt="labels[slot]" />
        </span>
      </button>
    </div>

    <div
      v-if="roundVerdict"
      class="rps-verdict"
      :class="{
        'rps-verdict--win': roundVerdict === 'win',
        'rps-verdict--lose': roundVerdict === 'lose',
        'rps-verdict--tie': roundVerdict === 'tie',
      }"
      role="status"
    >
      <span v-if="roundVerdict === 'win'" class="rps-verdict-icon" aria-hidden="true">✓</span>
      <span v-else-if="roundVerdict === 'lose'" class="rps-verdict-icon rps-verdict-icon--x" aria-hidden="true">✕</span>
      <span v-else class="rps-verdict-icon rps-verdict-icon--tie" aria-hidden="true">=</span>
      <span class="rps-verdict-text">
        {{ roundVerdict === 'win' ? t('rps.verdict.win') : roundVerdict === 'lose' ? t('rps.verdict.lose') : t('rps.verdict.tie') }}
      </span>
    </div>

    <p class="rps-board-label rps-board-label--you">{{ t('rps.youChoice') }}</p>
    <div class="rps-card-row">
      <button
        v-for="move in playerMoves"
        :key="'you-' + move"
        type="button"
        class="rps-card rps-card--you"
        :class="{
          'rps-card--selected': selected === move && !opponentRevealed,
          'rps-card--win': playerWinClass(move),
        }"
        :disabled="disabled"
        :aria-pressed="selected === move"
        :aria-label="labels[move]"
        @click="onPick(move)"
      >
        <img class="rps-card-single" :src="faces[move]" :alt="labels[move]" />
        <span v-if="showPickMark && selected === move" class="rps-card-mark" aria-hidden="true">✓</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.rps-board {
  margin: 12px 0;
}
.rps-board-label {
  margin: 0 0 10px;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  opacity: 0.75;
}
.rps-board-label--you {
  margin-top: 4px;
}
.rps-card-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  max-width: min(840px, 100%);
  width: 100%;
}
.rps-card {
  position: relative;
  aspect-ratio: 1;
  padding: 0;
  border: none;
  border-radius: 16px;
  background: transparent;
  cursor: default;
  perspective: 900px;
}
.rps-card--you {
  cursor: pointer;
  transition:
    box-shadow 0.22s ease,
    transform 0.22s ease;
}
.rps-card--you:not(:disabled):hover {
  transform: translateY(-3px);
}
.rps-card--you:disabled {
  cursor: not-allowed;
  opacity: 0.88;
}
.rps-card--selected {
  box-shadow:
    0 0 0 4px #ffeb3b,
    0 12px 32px rgba(255, 235, 59, 0.38);
  transform: translateY(-6px) scale(1.04);
}
.rps-card--win {
  box-shadow:
    0 0 0 4px #69f0ae,
    0 12px 36px rgba(105, 240, 174, 0.45);
}
.rps-card-inner {
  display: block;
  width: 100%;
  height: 100%;
  position: relative;
  transform-style: preserve-3d;
  transition: transform 0.55s cubic-bezier(0.4, 0.2, 0.2, 1);
}
.rps-card--flipped .rps-card-inner {
  transform: rotateY(180deg);
}
.rps-card-face {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 16px;
  backface-visibility: hidden;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
}
.rps-card-face--back {
  transform: rotateY(0deg);
}
.rps-card-face--front {
  transform: rotateY(180deg);
}
.rps-card-single {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
}
.rps-card-mark {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #ffeb3b;
  color: #1a1208;
  font-weight: 800;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.35);
  animation: rpsMarkPop 0.28s ease;
}
.rps-verdict {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 18px auto;
  padding: 14px 28px;
  border-radius: 999px;
  font-weight: 800;
  font-size: 1.35rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  animation: rpsVerdictIn 0.4s cubic-bezier(0.34, 1.4, 0.64, 1);
  max-width: min(840px, 100%);
}
.rps-verdict--win {
  background: linear-gradient(135deg, rgba(46, 125, 50, 0.95), rgba(102, 187, 106, 0.85));
  color: #e8f5e9;
  border: 2px solid rgba(165, 255, 180, 0.65);
  box-shadow: 0 8px 32px rgba(76, 175, 80, 0.45);
}
.rps-verdict--lose {
  background: linear-gradient(135deg, rgba(183, 28, 28, 0.95), rgba(229, 57, 53, 0.88));
  color: #ffebee;
  border: 2px solid rgba(255, 138, 128, 0.6);
  box-shadow: 0 8px 32px rgba(244, 67, 54, 0.45);
}
.rps-verdict--tie {
  background: linear-gradient(135deg, rgba(69, 90, 120, 0.9), rgba(96, 125, 139, 0.85));
  color: #eceff1;
  border: 2px solid rgba(176, 190, 197, 0.5);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}
.rps-verdict-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  background: rgba(255, 255, 255, 0.22);
}
.rps-verdict-icon--x {
  font-size: 1.35rem;
  line-height: 1;
}
.rps-verdict-icon--tie {
  font-size: 1.2rem;
  font-weight: 900;
}
@keyframes rpsMarkPop {
  from {
    transform: scale(0.35);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
@keyframes rpsVerdictIn {
  from {
    opacity: 0;
    transform: scale(0.7) translateY(8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
</style>
