<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { playSfx } from '../../audio/sound'
import { startHeartbeat, stopHeartbeat } from '../../telemetry/heartbeat'
import { startPresencePing, stopPresencePing } from '../../telemetry/presence'
import {
  tamagochiAction,
  tamagochiAdopt,
  tamagochiBuy,
  tamagochiEndVisit,
  tamagochiExchange,
  tamagochiHealCoins,
  tamagochiMe,
  tamagochiShop,
  type PetType
} from './api'
import { useTamagochiSocket } from './useTamagochiSocket'

const GAME_KEY = 'tamagochi_world_game'

const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const adoptType = ref<PetType>('cat')
const error = ref<string | null>(null)
/** После adopt: REST уже с питомцем, мир подтягивает его по WS — показываем лоадер на карте. */
const waitingPetWorldSync = ref(false)
const adoptBusy = ref(false)

const me = ref<any>(null)
const shop = ref<any>(null)
const shopError = ref<string | null>(null)
const shopSuccess = ref('')
const { pets, pickups, events, mePet, payload: wsPayload, lastError } = useTamagochiSocket(auth.token)

const mapFieldRef = ref<HTMLElement | null>(null)
const diamondHudRef = ref<HTMLElement | null>(null)
const tickNow = ref(Date.now())
const diamondFlights = ref<Array<{ id: string; x0: number; y0: number; x1: number; y1: number }>>([])

const diamondSearchMs = computed(
  () => Math.round((Number(wsPayload.value?.world?.diamond_search_duration_sec) || 15) * 1000)
)

const myDiamondSearchPct = computed(() => {
  const until = mePet.value?.ability?.diamond_search_until
  if (!until) return null
  const end = Date.parse(String(until))
  if (!Number.isFinite(end)) return null
  const start = end - diamondSearchMs.value
  const p = ((tickNow.value - start) / diamondSearchMs.value) * 100
  return Math.max(0, Math.min(100, p))
})

type EncounterHud = { pct: number; kind: 'play' | 'fight'; label: string }

function computeEncounterProgress(p: any): EncounterHud | null {
  const act = String(p?.activity ?? '')
  if (act !== 'playing_with_other' && act !== 'fighting') return null
  const until = p?.activity_until
  if (!until) return null
  const end = Date.parse(String(until))
  if (!Number.isFinite(end)) return null
  const playMs = Math.round((Number(wsPayload.value?.world?.pet_play_duration_sec) || 5) * 1000)
  const fightMs = Math.round((Number(wsPayload.value?.world?.pet_fight_duration_sec) || 30) * 1000)
  const dur = act === 'fighting' ? fightMs : playMs
  const start = end - dur
  const pct = Math.max(0, Math.min(100, ((tickNow.value - start) / dur) * 100))
  const label = act === 'fighting' ? 'Драка' : 'Игра с другим'
  const kind: 'play' | 'fight' = act === 'fighting' ? 'fight' : 'play'
  return { pct, kind, label }
}

const myEncounterProgress = computed((): EncounterHud | null => {
  void tickNow.value
  void wsPayload.value?.world?.pet_play_duration_sec
  void wsPayload.value?.world?.pet_fight_duration_sec
  const mine = (pets.value ?? []).find((x: any) => x?.owner === auth.username)
  return mine ? computeEncounterProgress(mine) : null
})

const PET_TYPES: PetType[] = ['cat', 'dog', 'pokemon', 'capybara', 'alien']

const PET_LABEL_RU: Record<PetType, string> = {
  cat: 'Кот',
  dog: 'Собака',
  pokemon: 'Покемон',
  capybara: 'Капибара',
  alien: 'Пришелец'
}

/** Подписи к покупке еды по типу питомца */
const PET_FOOD_FOR_RU: Record<PetType, string> = {
  cat: 'для кота',
  dog: 'для собаки',
  pokemon: 'для покемона',
  capybara: 'для капибары',
  alien: 'для пришельца'
}

const ACTIVITY_RU: Record<string, string> = {
  wandering: 'гуляет',
  moving: 'идёт',
  sleeping: 'спит',
  fighting: 'Драка',
  playing_with_other: 'играет с другим',
  eating_map_food: 'ест с земли',
  digging: 'роет',
  hunting: 'охотится',
  sparking: 'искрит',
  relaxing: 'отдыхает',
  scanning: 'сканирует',
  exploring: 'исследует'
}

function activityRu(code: string | undefined): string {
  const k = String(code ?? '')
  return ACTIVITY_RU[k] ?? (k || '—')
}

const myPet = computed(() => mePet.value ?? me.value?.pet ?? null)
const hasPet = computed(() => !!myPet.value)

const coinsWallet = computed(() => Number(shop.value?.wallet?.coins ?? 0))
const exchangeRate = computed(() => Number(shop.value?.prices?.diamonds_to_coins_rate ?? 0))
const foodCoinCost = computed(() => Number(shop.value?.prices?.food_diamonds ?? 0) * exchangeRate.value)
const toyCoinCost = computed(() => Number(shop.value?.prices?.toy_diamonds ?? 0) * exchangeRate.value)
const canBuyAnyFood = computed(() => foodCoinCost.value > 0 && coinsWallet.value >= foodCoinCost.value)
const canBuyToy = computed(() => toyCoinCost.value > 0 && coinsWallet.value >= toyCoinCost.value)

const HEAL_HP_COST_COINS = 30
const PLAY_ACTION_COINS_COST = 25
const SLEEP_ACTION_COINS_COST = 10

const diamondsBalance = computed(() => Number((auth.otherData as any).diamonds ?? 0))
const canExchangeOneDiamond = computed(() => diamondsBalance.value >= 1 && exchangeRate.value > 0)

const hud = computed(() => {
  const p = myPet.value
  const s = p?.stats ?? {}
  return {
    hp: Number(s.hp ?? 0),
    hunger: Number(s.hunger ?? 0),
    sleepiness: Number(s.sleepiness ?? 0),
    mood: Number(s.mood ?? 0),
    sleeping: !!p?.is_sleeping,
    activity: String(p?.activity ?? 'wandering')
  }
})

const foodByType = computed(() => (shop.value?.inventory?.food_by_type ?? {}) as Record<string, number>)

const foodCountForPet = computed(() => {
  const t = String(myPet.value?.type ?? 'cat')
  return Number(foodByType.value[t] ?? 0)
})

/** Имена файлов в backend/app/games/tamagochi_world/pictures/ (как у тебя на диске) */
const FOOD_FILE: Record<PetType, string> = {
  cat: 'cat_food.png',
  dog: 'dog_food.png',
  pokemon: 'pocemon_food.png',
  capybara: 'capybara_food.png',
  alien: 'alien_food.png'
}

const AVATAR_FILE: Record<PetType, string> = {
  cat: 'pet_cat.png',
  dog: 'pet_dog.png',
  pokemon: 'pet_pokemon.png',
  capybara: 'pet_capybara.png',
  alien: 'pet_alien.png'
}

function pictureFood(type: string) {
  const key = type as PetType
  const file = FOOD_FILE[key] ?? `food_${type}.png`
  return `/tamagochi/pictures/${file}`
}

function pictureAvatar(type: string) {
  const key = type as PetType
  const file = AVATAR_FILE[key] ?? `avatar_${type}.png`
  return `/tamagochi/pictures/${file}`
}

const bars = computed(() => {
  const hp = Math.max(0, Math.min(100, hud.value.hp))
  const fullness = Math.max(0, Math.min(100, 100 - hud.value.hunger))
  const energy = Math.max(0, Math.min(100, 100 - hud.value.sleepiness))
  const mood = Math.max(0, Math.min(100, hud.value.mood))
  return { hp, fullness, energy, mood }
})

const diamondMeta = computed(() => wsPayload.value?.me?.diamond_info ?? null)

function fmtToyPassiveHours(h: number): string {
  if (!Number.isFinite(h) || h <= 0) return '—'
  if (h >= 48) return `${Math.round(h / 24)} сут.`
  if (h >= 1) return `${h.toFixed(1)} ч`
  return `${Math.max(1, Math.round(h * 60))} мин`
}

const canHealWithCoins = computed(
  () => hasPet.value && coinsWallet.value >= HEAL_HP_COST_COINS && bars.value.hp < 100,
)

const canPlayWithCoins = computed(
  () => hasPet.value && !hud.value.sleeping && coinsWallet.value >= PLAY_ACTION_COINS_COST,
)

const canSleepWithCoins = computed(
  () => hasPet.value && !hud.value.sleeping && coinsWallet.value >= SLEEP_ACTION_COINS_COST,
)

async function loadMe() {
  error.value = null
  try {
    const data = await tamagochiMe(auth.token)
    me.value = data
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function loadShop() {
  shopError.value = null
  try {
    shop.value = await tamagochiShop(auth.token)
  } catch (e: any) {
    shopError.value = String(e?.message ?? e)
  }
}

function waitForMePetOnWorld(maxMs = 22000): Promise<void> {
  return new Promise((resolve) => {
    if (mePet.value != null && mePet.value.alive !== false) {
      resolve()
      return
    }
    let done = false
    const finish = () => {
      if (done) return
      done = true
      stop()
      window.clearTimeout(timer)
      resolve()
    }
    const stop = watch(
      mePet,
      (p) => {
        if (p != null && p.alive !== false) finish()
      },
      { flush: 'post' },
    )
    const timer = window.setTimeout(finish, maxMs)
  })
}

async function adopt() {
  if (adoptBusy.value) return
  playSfx('button')
  error.value = null
  waitingPetWorldSync.value = false
  adoptBusy.value = true
  try {
    await tamagochiAdopt(auth.token, adoptType.value)
    await Promise.all([loadMe(), loadShop()])
    if (mePet.value != null && mePet.value.alive !== false) {
      return
    }
    waitingPetWorldSync.value = true
    try {
      await waitForMePetOnWorld()
    } finally {
      waitingPetWorldSync.value = false
    }
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    waitingPetWorldSync.value = false
  } finally {
    adoptBusy.value = false
  }
}

async function act(type: 'feed' | 'play' | 'sleep' | 'wake') {
  playSfx('button')
  error.value = null
  try {
    await tamagochiAction(auth.token, type, null)
    await Promise.all([loadMe(), loadShop()])
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function healHpCoins() {
  playSfx('button')
  error.value = null
  try {
    await tamagochiHealCoins(auth.token)
    await Promise.all([loadMe(), loadShop()])
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function exchangeOneDiamond() {
  playSfx('button')
  shopError.value = null
  try {
    await tamagochiExchange(auth.token, 1)
    await loadShop()
    await auth.refreshProfile()
  } catch (e: any) {
    shopError.value = String(e?.message ?? e)
  }
}

async function buyFoodOne(forType: PetType) {
  playSfx('button')
  shopError.value = null
  try {
    await tamagochiBuy(auth.token, 'food', 1, forType)
    await loadShop()
  } catch (e: any) {
    shopError.value = String(e?.message ?? e)
  }
}

async function buyToyOne() {
  playSfx('button')
  shopError.value = null
  shopSuccess.value = ''
  try {
    await tamagochiBuy(auth.token, 'toy', 1)
    await loadShop()
    shopSuccess.value =
      'Игрушка активна: настроение падает медленнее (~24 ч с покупки, суммируется), буст частоты поиска алмазов — 10 минут (суммируется). Смотри блок «Поиск алмазов» слева.'
    window.setTimeout(() => {
      shopSuccess.value = ''
    }, 8000)
  } catch (e: any) {
    shopError.value = String(e?.message ?? e)
  }
}

async function clickMove(ev: MouseEvent) {
  if (!hasPet.value) return
  const field = ev.currentTarget as HTMLElement
  const rect = field.getBoundingClientRect()
  const x = (ev.clientX - rect.left) / rect.width
  const y = (ev.clientY - rect.top) / rect.height
  const w = Number((wsPayload.value?.world?.w ?? 20800) || 20800)
  const h = Number((wsPayload.value?.world?.h ?? 20800) || 20800)
  try {
    await tamagochiAction(auth.token, 'move_to', { x: x * w, y: y * h })
  } catch {}
}

function petStyle(p: any) {
  const pos = p?.pos ?? { x: 0, y: 0 }
  const worldW = Number((wsPayload.value?.world?.w ?? 20800) || 20800)
  const worldH = Number((wsPayload.value?.world?.h ?? 20800) || 20800)
  const left = (Number(pos.x ?? 0) / worldW) * 100
  const top = (Number(pos.y ?? 0) / worldH) * 100
  return {
    left: `${left}%`,
    top: `${top}%`
  }
}

function pickupStyle(pk: any) {
  return petStyle({ pos: pk?.pos })
}

const petsToRender = computed(() => pets.value)
const pickupsToRender = computed(() => pickups.value ?? [])

const fx = ref<Array<{ id: string; kind: string; x: number; y: number; owner?: string }>>([])
let fxId = 0
function pushFx(kind: string, pos: any, owner?: string) {
  const worldW = Number((wsPayload.value?.world?.w ?? 20800) || 20800)
  const worldH = Number((wsPayload.value?.world?.h ?? 20800) || 20800)
  const x = (Number(pos?.x ?? 0) / worldW) * 100
  const y = (Number(pos?.y ?? 0) / worldH) * 100
  const id = `${Date.now()}_${fxId++}`
  fx.value.push({ id, kind, x, y, owner })
  window.setTimeout(() => {
    fx.value = fx.value.filter((f) => f.id !== id)
  }, 1800)
}

function launchDiamondFly(pos: { x?: number; y?: number }) {
  void nextTick(() => {
    const mapEl = mapFieldRef.value
    const hudEl = diamondHudRef.value
    if (!mapEl || !hudEl) return
    const mr = mapEl.getBoundingClientRect()
    const hr = hudEl.getBoundingClientRect()
    const worldW = Number(wsPayload.value?.world?.w ?? 20800)
    const worldH = Number(wsPayload.value?.world?.h ?? 20800)
    const px = (Number(pos?.x ?? 0) / worldW) * mr.width + mr.left
    const py = (Number(pos?.y ?? 0) / worldH) * mr.height + mr.top
    const x1 = hr.left + hr.width / 2
    const y1 = hr.top + hr.height / 2
    const id = `df_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    diamondFlights.value = [...diamondFlights.value, { id, x0: px, y0: py, x1, y1 }]
    window.setTimeout(() => {
      diamondFlights.value = diamondFlights.value.filter((d) => d.id !== id)
    }, 950)
  })
}

let lastEventTs = 0
function handleEvents() {
  const evs = events.value ?? []
  for (const ev of evs) {
    const at = String(ev?.at ?? '')
    const ts = Date.parse(at)
    if (!at || !Number.isFinite(ts) || ts <= lastEventTs) continue
    lastEventTs = ts
    if (ev.type === 'diamond_found') {
      const owner = String(ev?.owner ?? '')
      if (owner && owner === auth.username) {
        playSfx('diamond')
        void auth.refreshProfile()
        launchDiamondFly(ev.pos ?? {})
      } else {
        pushFx('diamond', ev.pos, ev.owner)
      }
    }
    if (ev.type === 'pet_play') {
      // show sparkle roughly at my pet (good enough visually)
      const p = myPet.value?.pos ?? { x: 0, y: 0 }
      pushFx('sparkle', p)
    }
  }
}

onMounted(async () => {
  await auth.refreshProfile()
  startHeartbeat(auth.token, GAME_KEY)
  startPresencePing(auth.token, GAME_KEY)
  await Promise.all([loadMe(), loadShop()])
  loading.value = false
  const t = window.setInterval(handleEvents, 300)
  const ui = window.setInterval(() => {
    tickNow.value = Date.now()
  }, 100)
  onBeforeUnmount(() => {
    window.clearInterval(t)
    window.clearInterval(ui)
  })
})

onBeforeUnmount(() => {
  waitingPetWorldSync.value = false
  adoptBusy.value = false
  stopHeartbeat()
  stopPresencePing()
  void tamagochiEndVisit(auth.token)
})

function exit() {
  playSfx('button')
  router.push('/games')
}

const showGuide = ref(false)

function openGuide() {
  playSfx('button')
  showGuide.value = true
}

function closeGuide() {
  showGuide.value = false
}
</script>

<template>
  <main class="page page-menu">
    <section v-if="lastError" class="panel tamagochi-ws-full">
      <div class="tamagochi-alert tamagochi-alert--blocking">
        <p class="tamagochi-ws-error-title">Подключение к полю</p>
        <p>{{ lastError }}</p>
        <button type="button" class="btn" style="margin-top: 12px; height: 44px" @click="exit">К играм</button>
      </div>
    </section>
    <section v-else class="panel panel-tamagochi" style="display:flex; gap:12px; align-items:stretch;">
      <aside class="tamagochi-aside">
        <div class="tamagochi-head-row">
          <h3 class="tamagochi-title">Тамагочи World</h3>
          <button type="button" class="btn btn-guide-tiny" @click="openGuide">Обучение</button>
        </div>
        <div style="display:grid; gap:10px;">
          <div v-if="error" class="tamagochi-alert">
            {{ error }}
          </div>

          <template v-if="!loading && !hasPet">
            <div style="opacity:0.9;">У тебя нет питомца. Выбери тип и нажми «Завести».</div>
            <div class="pet-type-picker" role="group" aria-label="Тип питомца" :class="{ 'pet-type-picker--disabled': adoptBusy }">
              <button
                v-for="t in PET_TYPES"
                :key="'adopt-' + t"
                type="button"
                class="pet-type-card"
                :disabled="adoptBusy"
                :class="{ 'pet-type-card--selected': adoptType === t }"
                :aria-pressed="adoptType === t"
                @click="adoptType = t"
              >
                <span class="pet-type-card-avatar" :class="'avatar-bg-' + t">
                  <img
                    class="pet-type-card-img"
                    :src="pictureAvatar(t)"
                    :alt="PET_LABEL_RU[t]"
                    @error="($event.target as HTMLImageElement).style.visibility = 'hidden'"
                  />
                </span>
                <span class="pet-type-card-name">{{ PET_LABEL_RU[t] }}</span>
              </button>
            </div>
            <button class="btn" :disabled="adoptBusy" @click="adopt" style="height: 44px;">
              {{ adoptBusy ? 'Подождите…' : 'Завести питомца' }}
            </button>
          </template>

          <template v-else>
            <div style="display:grid; gap:8px;">
              <div style="opacity:0.9;"><b>Состояние</b>: {{ activityRu(hud.activity) }}</div>

              <div>
                <div class="stat-row">
                  <span><b>Здоровье</b></span><span>{{ bars.hp }}%</span>
                </div>
                <div class="bar"><div class="fill hp" :style="{ width: `${bars.hp}%` }"></div></div>
              </div>
              <div>
                <div class="stat-row">
                  <span><b>Сытость</b></span><span>{{ bars.fullness }}%</span>
                </div>
                <div class="bar"><div class="fill food" :style="{ width: `${bars.fullness}%` }"></div></div>
              </div>
              <div>
                <div class="stat-row">
                  <span><b>Настроение</b></span><span>{{ bars.mood }}%</span>
                </div>
                <div class="bar"><div class="fill mood" :style="{ width: `${bars.mood}%` }"></div></div>
              </div>
              <div>
                <div class="stat-row">
                  <span><b>Бодрость</b></span><span>{{ bars.energy }}%</span>
                </div>
                <div class="bar"><div class="fill energy" :style="{ width: `${bars.energy}%` }"></div></div>
              </div>

              <div v-if="diamondMeta" class="tama-diamond-panel">
                <div class="tama-diamond-panel-title">Поиск алмазов на карте</div>
                <template v-if="diamondMeta.blocked">
                  <p class="tama-diamond-panel-muted">
                    Сейчас не запускается: среднее самочувствие по четырём шкалам ниже порога
                    ({{ diamondMeta.avg_wellbeing ?? '—' }}%; нужно примерно от 38%). Корми, дай выспаться и подними настроение.
                  </p>
                </template>
                <template v-else>
                  <div class="tama-diamond-pace-row">
                    <span>Активность поиска</span>
                    <span class="tama-diamond-pace-num">{{ diamondMeta.pace_percent }}%</span>
                  </div>
                  <div class="bar tama-diamond-pace-bar">
                    <div class="fill tama-diamond-pace-fill" :style="{ width: `${diamondMeta.pace_percent}%` }"></div>
                  </div>
                  <p class="tama-diamond-hint">
                    Чем выше шкала, тем чаще питомец может начинать поиск. Ориентир паузы между попытками в среднем
                    <b>~{{ diamondMeta.estimated_cooldown_minutes ?? '—' }}</b> мин (есть случайный разброс).
                  </p>
                </template>
                <div
                  v-if="diamondMeta.toy_passive_hours_left != null && diamondMeta.toy_passive_hours_left > 0"
                  class="tama-toy-line"
                >
                  🧸 Игрушка (настроение): ещё <b>{{ fmtToyPassiveHours(diamondMeta.toy_passive_hours_left) }}</b>
                </div>
                <div
                  v-if="diamondMeta.toy_diamond_boost && diamondMeta.toy_diamond_minutes_left != null"
                  class="tama-toy-line tama-toy-line--boost"
                >
                  ✦ Буст поиска алмазов: ещё <b>{{ Math.max(1, Math.ceil(diamondMeta.toy_diamond_minutes_left)) }} мин</b>
                </div>
              </div>

              <div style="opacity:0.85; font-size:12px;">Спит: {{ hud.sleeping ? 'да' : 'нет' }}</div>
            </div>

            <div style="display:grid; gap:8px; margin-top:10px;">
              <button class="btn" :disabled="foodCountForPet <= 0" @click="act('feed')" style="height: 44px;">
                Покормить <span style="opacity:0.8;">({{ PET_FOOD_FOR_RU[String(myPet?.type) as PetType] ?? myPet?.type }}: {{ foodCountForPet }} шт.)</span>
              </button>
              <div class="tama-play-heal-row">
                <button class="btn" :disabled="!canPlayWithCoins" @click="act('play')" style="height: 44px;">
                  Поиграть ({{ PLAY_ACTION_COINS_COST }} 🪙)
                </button>
                <button
                  class="btn btn-heal"
                  :disabled="!canHealWithCoins"
                  style="height: 44px;"
                  title="Добавляет 10% к шкале HP"
                  @click="healHpCoins"
                >
                  +10% HP ({{ HEAL_HP_COST_COINS }} 🪙)
                </button>
              </div>
              <button class="btn" :disabled="!canSleepWithCoins" @click="act('sleep')" style="height: 44px;">
                Уложить спать ({{ SLEEP_ACTION_COINS_COST }} 🪙)
              </button>
              <button class="btn" @click="act('wake')" style="height: 44px;">Разбудить</button>
            </div>

            <div class="shop-wrap">
              <h4 class="shop-heading">Магазин</h4>
              <p class="shop-lead">Один тап — одна покупка. Расчёт в <b>монетах</b>; цены и курс обновляются каждый час.</p>
              <div v-if="shopError" class="tamagochi-alert">
                {{ shopError }}
              </div>
              <div v-if="shopSuccess" class="tamagochi-shop-success">
                {{ shopSuccess }}
              </div>

              <div ref="diamondHudRef" class="shop-wallet">
                <div class="shop-wallet-item">
                  <span class="shop-wallet-label">Алмазы</span>
                  <span class="shop-wallet-value">💎 {{ (auth.otherData as any).diamonds ?? 0 }}</span>
                </div>
                <div class="shop-wallet-item">
                  <span class="shop-wallet-label">Монеты</span>
                  <span class="shop-wallet-value">🪙 {{ shop?.wallet?.coins ?? 0 }}</span>
                </div>
              </div>

              <button type="button" class="btn shop-exchange-btn" :disabled="!canExchangeOneDiamond" @click="exchangeOneDiamond">
                Обменять <b>1</b> 💎 на <b>{{ exchangeRate || '…' }}</b> монет
              </button>

              <div class="shop-section">
                <div class="shop-section-head">
                  <span class="shop-section-title">Еда</span>
                  <span class="shop-section-price">{{ foodCoinCost || '—' }} мон. за шт.</span>
                </div>
                <div class="shop-grid-food">
                  <div
                    v-for="t in PET_TYPES"
                    :key="'food-card-' + t"
                    class="shop-card"
                    :class="{ 'shop-card--accent': t === String(myPet?.type) }"
                  >
                    <img :src="pictureFood(t)" class="shop-card-icon" :alt="PET_FOOD_FOR_RU[t]" @error="($event.target as HTMLImageElement).style.display='none'" />
                    <div class="shop-card-title">{{ PET_FOOD_FOR_RU[t] }}</div>
                    <div class="shop-card-meta">В запасе: {{ foodByType[t] ?? 0 }}</div>
                    <button
                      type="button"
                      class="btn shop-card-buy"
                      :disabled="!canBuyAnyFood"
                      @click="buyFoodOne(t)"
                    >
                      Купить
                    </button>
                  </div>
                </div>
              </div>

              <div class="shop-section">
                <div class="shop-section-head">
                  <span class="shop-section-title">Игрушка</span>
                  <span class="shop-section-price">{{ toyCoinCost || '—' }} мон. за шт.</span>
                </div>
                <div class="shop-card shop-card--toy">
                  <div class="shop-card-toy-row">
                    <span class="shop-toy-emoji">🧸</span>
                    <div>
                      <div class="shop-card-title">Буст настроения</div>
                      <div class="shop-card-meta">В рюкзаке: {{ shop?.inventory?.toy ?? 0 }}</div>
                    </div>
                  </div>
                  <button type="button" class="btn shop-card-buy" :disabled="!canBuyToy" @click="buyToyOne">Купить</button>
                </div>
              </div>

              <details class="shop-details">
                <summary>Что дают предметы</summary>
                <div class="shop-details-body">
                  <div><b>Еда</b>: {{ shop?.effects?.food?.desc ?? '' }}</div>
                  <div><b>Игрушка</b>: {{ shop?.effects?.toy?.desc ?? '' }}</div>
                </div>
              </details>
            </div>
          </template>

          <button type="button" class="btn btn-guide-secondary" @click="openGuide">Как работают параметры</button>
          <button class="btn" @click="exit" style="height: 44px; margin-top: 10px;">К играм</button>
        </div>
      </aside>

      <section class="tamagochi-map-section">
        <h3 class="tamagochi-map-section-title">Карта мира</h3>
        <div class="tamagochi-map-stage">
          <div
            v-if="waitingPetWorldSync"
            class="tamagochi-pet-wait-overlay"
            role="status"
            aria-live="polite"
            aria-busy="true"
          >
            <div class="tamagochi-pet-wait-card">
              <div class="tamagochi-pet-wait-spinner" aria-hidden="true" />
              <p class="tamagochi-pet-wait-title">Готовим питомца на поле</p>
              <p class="tamagochi-pet-wait-text">
                Питомец уже создан — он появится на карте через несколько секунд. Это нормально, подождите.
              </p>
            </div>
          </div>
          <div ref="mapFieldRef" class="field tamagochi-map" @click="clickMove">
          <div class="gridBg"></div>
          <div
            v-for="pk in pickupsToRender"
            :key="'pk-' + pk.id"
            class="map-food"
            :style="{
              position: 'absolute',
              transform: 'translate(-50%, -50%)',
              ...pickupStyle(pk)
            }"
          >
            <img
              class="map-food-img"
              :src="pictureFood(pk.for_type)"
              :alt="PET_LABEL_RU[String(pk.for_type) as PetType] ?? String(pk.for_type)"
            />
          </div>
          <div
            v-for="p in petsToRender"
            :key="p.owner"
            class="pet"
            :style="{
              position: 'absolute',
              transform: 'translate(-50%, -50%)',
              width: '58px',
              height: '58px',
              borderRadius: '14px',
              display: 'grid',
              placeItems: 'center',
              background: p.owner === auth.username ? 'rgba(120,220,160,0.18)' : 'rgba(255,255,255,0.08)',
              border: p.owner === auth.username ? '1px solid rgba(120,220,160,0.35)' : '1px solid rgba(255,255,255,0.16)',
              color: 'rgba(255,255,255,0.92)',
              fontSize: '11px',
              userSelect: 'none',
              animation: p.activity === 'moving' ? 'bob 0.8s ease-in-out infinite' : 'idle 1.4s ease-in-out infinite',
              ...petStyle(p)
            }"
            :title="`${p.owner} • ${PET_LABEL_RU[String(p.type) as PetType] ?? p.type} • настроение: ${p.stats?.mood ?? 0}${p.online ? ' • в сети' : ''}`"
          >
            <div
              v-if="p.owner === auth.username && (myEncounterProgress || myDiamondSearchPct !== null)"
              class="pet-bars-stack"
            >
              <div
                v-if="myEncounterProgress"
                class="encounter-progress-wrap"
                :class="
                  myEncounterProgress.kind === 'fight'
                    ? 'encounter-progress-wrap--fight'
                    : 'encounter-progress-wrap--play'
                "
              >
                <div class="encounter-progress-label">{{ myEncounterProgress.label }}</div>
                <div class="encounter-progress-track">
                  <div
                    class="encounter-progress-fill"
                    :style="{ width: `${myEncounterProgress.pct}%` }"
                  ></div>
                </div>
              </div>
              <div
                v-if="p.owner === auth.username && myDiamondSearchPct !== null"
                class="diamond-progress-wrap"
                title="Поиск алмаза — любая команда или поедание еды с карты сбросит прогресс"
              >
                <div class="diamond-progress-label">Поиск алмаза</div>
                <div class="diamond-progress-track">
                  <div class="diamond-progress-fill" :style="{ width: `${myDiamondSearchPct}%` }"></div>
                </div>
              </div>
            </div>
            <div style="position:absolute; top:-18px; left:50%; transform: translateX(-50%); font-size:12px; font-weight:700; text-shadow: 0 2px 10px rgba(0,0,0,0.6);">
              {{ p.owner }}
            </div>
            <div class="pet-avatar-box" :class="'avatar-bg-' + String(p.type)">
              <img
                class="pet-avatar"
                :src="pictureAvatar(String(p.type))"
                :alt="PET_LABEL_RU[String(p.type) as PetType] ?? String(p.type)"
                @error="($event.target as HTMLImageElement).style.visibility = 'hidden'"
              />
            </div>
            <div style="position:absolute; bottom:-16px; left:50%; transform: translateX(-50%); font-size:11px; opacity:0.9;">
              {{ activityRu(p.activity) }}
            </div>
          </div>

          <div
            v-for="f in fx"
            :key="f.id"
            :style="{
              position: 'absolute',
              left: `${f.x}%`,
              top: `${f.y}%`,
              transform: 'translate(-50%, -50%)',
              pointerEvents: 'none'
            }"
          >
            <img v-if="f.kind==='diamond'" src="/assets/original/brilliant.png" style="width:42px; height:26px; animation: floatUp 1.8s ease-out forwards;" />
            <div v-else class="sparkle"></div>
          </div>
        </div>
        </div>
        <div style="margin-top:10px; opacity:0.85; font-size: 13px;">
          Клик по полю — команда питомцу идти в точку. С чужими питомцами нельзя взаимодействовать, можно только наблюдать.
        </div>
      </section>
    </section>
  </main>
  <Teleport to="body">
    <div v-if="showGuide" class="guide-backdrop" @click.self="closeGuide">
      <div class="guide-modal" role="dialog" aria-modal="true" aria-labelledby="guide-title">
        <div class="guide-modal-head">
          <h2 id="guide-title" class="guide-title">Обучение</h2>
          <button type="button" class="guide-close" aria-label="Закрыть" @click="closeGuide">×</button>
        </div>
        <div class="guide-body">
          <section class="guide-section">
            <h3>Что за полоски</h3>
            <p>
              У питомца четыре шкалы: <b>здоровье</b>, <b>сытость</b>, <b>настроение</b> и <b>бодрость</b>.
              Сытость — это «наелся или хочет есть»: чем выше полоска, тем он сытее.
              Бодрость — как силы: побежал, поиграл — силы меньше, поспал — снова больше.
            </p>
          </section>
          <section class="guide-section">
            <h3>Как восстановить здоровье</h3>
            <ul>
              <li><b>Поспать</b> — во сне здоровье медленно поднимается, если питомец не очень голоден.</li>
              <li>
                Кнопка <b>«+10% HP»</b> рядом с «Поиграть» — моментально добавляет 10 процентов за <b>30 монет</b>
                (если монет хватает и здоровье ещё не полное).
              </li>
              <li>Не давай сильно проголодаться и не переутомляй — от этого здоровье может падать.</li>
            </ul>
          </section>
          <section class="guide-section">
            <h3>Как восстановить сытость</h3>
            <p>
              Нажми <b>«Покормить»</b>, если в запасе есть еда для твоего типа питомца. Еду покупаешь в магазине за монеты.
              Во сне тоже немного хочется есть, но медленнее, чем когда он бегает наяву.
            </p>
          </section>
          <section class="guide-section">
            <h3>Как поднять настроение</h3>
            <p>
              Нажми <b>«Поиграть»</b> — команда стоит <b>25 монет</b>. Игрушку из магазина можно использовать, чтобы настроение падало не так быстро.
              Голод и плохое самочувствие настроение портят — корми и следи за здоровьем.
            </p>
          </section>
          <section class="guide-section">
            <h3>Как восстановить бодрость</h3>
            <p>
              Уложи спать кнопкой <b>«Уложить спать»</b> (<b>10 монет</b>). Примерно за <b>10 часов</b> непрерывного сна бодрость с нуля
              дорастёт до максимума. На бодрствовании силы тратятся: обычно полная шкала садится примерно за
              <b>от 6 до 14 часов</b> — зависит от того, чем он занят и как себя чувствует.
              Если бодрость упала до нуля, питомец <b>сам уснёт</b>.
            </p>
          </section>
          <section class="guide-section">
            <h3>Про алмазы</h3>
            <p>
              Питомец сам ищет алмазы на карте, когда он в форме. Если <b>среднее самочувствие</b> по четырём шкалам
              (здоровье, сытость, бодрость, настроение) ниже порога, поиск не начинается — смотри индикатор «Активность
              поиска» в левой панели. Чем все показатели выше, тем чаще возможны попытки. Игрушка из магазина даёт
              пассивный бонус настроению на сутки (суммируется) и отдельный <b>буст частоты поиска на 10 минут</b>
              (тоже суммируется) — оставшееся время показывается там же.
            </p>
          </section>
          <section class="guide-section">
            <h3>Почему всё связано</h3>
            <p>
              Усталый, голодный или больной питомец быстрее теряет силы и хуже себя чувствует.
              Всё как у людей: поешь — легче на душе, выспался — больше энергии.
            </p>
          </section>
          <section class="guide-section">
            <h3>На карте с другими питомцами</h3>
            <p>
              Если один <b>спит</b>, они не будут играть и не подерутся. Но иногда бодрствующий может
              <b>разбудить</b> спящего — это случайность, примерно <b>один раз из двадцати</b>.
            </p>
          </section>
          <section class="guide-section guide-section--muted">
            <p class="guide-tip">
              Совет: перед долгой прогулкой по карте проверь бодрость и положи еду в запас.
            </p>
          </section>
        </div>
        <div class="guide-footer">
          <button type="button" class="btn" @click="closeGuide">Понятно</button>
        </div>
      </div>
    </div>
    <img
      v-for="d in diamondFlights"
      :key="d.id"
      src="/assets/original/brilliant.png"
      class="diamond-flight-img"
      alt=""
      :style="{
        '--dx': `${d.x1 - d.x0}px`,
        '--dy': `${d.y1 - d.y0}px`,
        left: `${d.x0}px`,
        top: `${d.y0}px`
      }"
    />
  </Teleport>
</template>

<style scoped>
.tamagochi-aside {
  flex: 0 0 380px;
  border-radius: 14px;
  padding: 14px;
  background: rgba(10, 14, 28, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.15);
}
.tamagochi-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.tamagochi-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.btn-guide-tiny {
  flex-shrink: 0;
  padding: 8px 12px;
  font-size: 13px;
  height: auto;
  background: linear-gradient(180deg, #3d5588, #2a3d62);
  border-color: rgba(140, 167, 255, 0.45);
}
.btn-guide-secondary {
  height: 42px;
  margin-top: 6px;
  background: linear-gradient(180deg, #3a5080, #273c63);
  border-color: rgba(140, 167, 255, 0.38);
  font-size: 14px;
}

.tama-play-heal-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.btn-heal {
  font-size: 13px;
  padding-left: 10px;
  padding-right: 10px;
  background: linear-gradient(180deg, #3d8f6a, #276348);
  border-color: rgba(140, 220, 180, 0.45);
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
  padding: 16px 18px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.guide-title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
}
.guide-close {
  border: none;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}
.guide-close:hover {
  background: rgba(255, 255, 255, 0.14);
}
.guide-body {
  padding: 14px 18px;
  overflow-y: auto;
  flex: 1;
  font-size: 14px;
  line-height: 1.55;
}
.guide-section {
  margin-bottom: 16px;
}
.guide-section h3 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 700;
  color: rgba(200, 215, 255, 0.98);
}
.guide-section p {
  margin: 0;
}
.guide-section ul {
  margin: 0;
  padding-left: 18px;
}
.guide-section li {
  margin-bottom: 8px;
}
.guide-section--muted {
  opacity: 0.92;
}
.guide-tip {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(80, 130, 220, 0.12);
  border: 1px solid rgba(120, 160, 255, 0.22);
}
.guide-footer {
  padding: 12px 18px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: flex-end;
}
.tamagochi-alert {
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 80, 80, 0.12);
  border: 1px solid rgba(255, 80, 80, 0.25);
}
.tamagochi-alert--blocking {
  padding: 16px 18px;
  font-size: 15px;
  line-height: 1.5;
}
.tamagochi-ws-full {
  max-width: 520px;
  margin: 0 auto 16px;
}
.tamagochi-ws-error-title {
  margin: 0 0 8px 0;
  font-size: 1.12rem;
  font-weight: 700;
}

.pet-type-picker {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.pet-type-picker--disabled {
  opacity: 0.55;
  pointer-events: none;
}
.pet-type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px 10px;
  border-radius: 14px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  background: rgba(10, 14, 28, 0.92);
  color: #f4f7ff;
  cursor: pointer;
  font: inherit;
  text-align: center;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    transform 0.12s ease;
}
.pet-type-card:hover {
  border-color: rgba(126, 166, 255, 0.55);
  transform: translateY(-1px);
}
.pet-type-card:focus-visible {
  outline: 2px solid rgba(126, 166, 255, 0.85);
  outline-offset: 2px;
}
.pet-type-card--selected {
  border-color: rgba(120, 220, 160, 0.8);
  box-shadow: 0 0 0 2px rgba(120, 220, 160, 0.28);
}
.pet-type-card-avatar {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.22);
  flex-shrink: 0;
}
.pet-type-card-img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}
.pet-type-card-name {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.25;
}

.tama-diamond-panel {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: linear-gradient(155deg, rgba(40, 70, 130, 0.28), rgba(12, 20, 42, 0.55));
  border: 1px solid rgba(130, 180, 255, 0.28);
  display: grid;
  gap: 8px;
}
.tama-diamond-panel-title {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0.92;
  color: rgba(210, 230, 255, 0.95);
}
.tama-diamond-panel-muted {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  opacity: 0.9;
  color: rgba(255, 210, 190, 0.95);
}
.tama-diamond-pace-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 12px;
  opacity: 0.92;
}
.tama-diamond-pace-num {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: rgba(160, 220, 255, 0.98);
}
.tama-diamond-pace-bar {
  height: 8px;
}
.tama-diamond-pace-fill {
  background: linear-gradient(90deg, #3a7dca, #6ec0ff);
  border-radius: 4px;
}
.tama-diamond-hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  opacity: 0.82;
}
.tama-toy-line {
  font-size: 12px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.tama-toy-line--boost {
  border-color: rgba(120, 200, 255, 0.35);
  background: rgba(30, 80, 140, 0.25);
}
.tamagochi-shop-success {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.4;
  background: rgba(60, 140, 95, 0.22);
  border: 1px solid rgba(120, 220, 160, 0.35);
  color: rgba(220, 255, 235, 0.96);
}

.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  opacity: 0.9;
}

.shop-wrap {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  display: grid;
  gap: 12px;
}
.shop-heading {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
}
.shop-lead {
  margin: 0;
  font-size: 12px;
  opacity: 0.88;
  line-height: 1.4;
}
.shop-wallet {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.shop-wallet-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.12);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.shop-wallet-label {
  font-size: 11px;
  opacity: 0.75;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.shop-wallet-value {
  font-size: 15px;
  font-weight: 700;
}
.shop-exchange-btn {
  width: 100%;
  min-height: 42px;
  font-size: 13px;
}
.shop-section {
  display: grid;
  gap: 10px;
}
.shop-section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.shop-section-title {
  font-weight: 700;
  font-size: 14px;
}
.shop-section-price {
  font-size: 12px;
  opacity: 0.85;
}
.shop-grid-food {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.shop-card {
  display: grid;
  gap: 8px;
  padding: 12px 10px;
  border-radius: 14px;
  background: linear-gradient(165deg, rgba(35, 48, 90, 0.55), rgba(12, 16, 32, 0.75));
  border: 1px solid rgba(120, 150, 255, 0.2);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.25);
  text-align: center;
}
.shop-card--accent {
  border-color: rgba(120, 220, 160, 0.45);
  box-shadow: 0 0 0 1px rgba(120, 220, 160, 0.2);
}
.shop-card-icon {
  width: 44px;
  height: 44px;
  object-fit: contain;
  margin: 0 auto;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 0, 0, 0.2);
}
.shop-card-title {
  font-size: 13px;
  font-weight: 700;
}
.shop-card-meta {
  font-size: 11px;
  opacity: 0.82;
}
.shop-card-buy {
  width: 100%;
  min-height: 36px;
  font-size: 13px;
  padding: 8px 10px;
}
.shop-card--toy {
  grid-template-columns: 1fr;
  text-align: left;
}
.shop-card-toy-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.shop-toy-emoji {
  font-size: 36px;
  line-height: 1;
}
.shop-details {
  font-size: 12px;
  opacity: 0.92;
}
.shop-details summary {
  cursor: pointer;
  font-weight: 600;
}
.shop-details-body {
  margin-top: 8px;
  line-height: 1.45;
  opacity: 0.9;
  display: grid;
  gap: 6px;
}

.bar {
  height: 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.10);
  border: 1px solid rgba(255, 255, 255, 0.14);
  overflow: hidden;
}
.fill {
  height: 100%;
  border-radius: 999px;
}
.fill.hp {
  background: linear-gradient(90deg, rgba(80, 255, 140, 0.95), rgba(80, 180, 255, 0.85));
}
.fill.food {
  background: linear-gradient(90deg, rgba(110, 255, 120, 0.90), rgba(255, 210, 80, 0.90));
}
.fill.mood {
  background: linear-gradient(90deg, rgba(255, 140, 240, 0.90), rgba(140, 200, 255, 0.90));
}
.fill.energy {
  background: linear-gradient(90deg, rgba(140, 200, 255, 0.90), rgba(80, 255, 200, 0.85));
}

/* Крупное поле: ширина секции после panel-tamagochi + потолок ~×6 к старому 3840px */
.tamagochi-map-section {
  flex: 1;
  border-radius: 14px;
  padding: 14px;
  background: rgba(10, 14, 28, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.12);
  position: relative;
  overflow: auto;
  min-width: 0;
}
.tamagochi-map-section-title {
  margin: 0 0 10px 0;
}
.tamagochi-map-stage {
  position: relative;
}
.tamagochi-pet-wait-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(8, 12, 24, 0.75);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-radius: 12px;
}
.tamagochi-pet-wait-card {
  max-width: 320px;
  padding: 22px 20px;
  text-align: center;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(20, 28, 48, 0.96);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}
.tamagochi-pet-wait-spinner {
  width: 44px;
  height: 44px;
  margin: 0 auto 14px;
  border-radius: 50%;
  border: 3px solid rgba(255, 255, 255, 0.14);
  border-top-color: rgba(120, 200, 255, 0.95);
  animation: tama-spin 0.85s linear infinite;
}
.tamagochi-pet-wait-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 800;
}
.tamagochi-pet-wait-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  opacity: 0.88;
}
@keyframes tama-spin {
  to {
    transform: rotate(360deg);
  }
}

.tamagochi-map {
  position: relative;
  box-sizing: border-box;
  width: min(100%, min(calc(100vw - 380px), calc(100dvh - 80px), 23040px));
  aspect-ratio: 1 / 1;
  margin: 0 auto;
  border-radius: 12px;
  background: radial-gradient(ellipse 120% 120% at 30% 30%, rgba(50, 80, 160, 0.28), rgba(10, 14, 28, 0.72));
  border: 1px solid rgba(255, 255, 255, 0.14);
  overflow: hidden;
}

.gridBg {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px);
  background-size: 64px 64px;
  opacity: 0.25;
  pointer-events: none;
}

.pet-avatar-box {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.18);
}
.avatar-bg-cat {
  background: radial-gradient(circle at 30% 30%, rgba(255, 170, 220, 0.9), rgba(120, 40, 120, 0.65));
}
.avatar-bg-dog {
  background: radial-gradient(circle at 30% 30%, rgba(255, 210, 140, 0.9), rgba(120, 70, 20, 0.65));
}
.avatar-bg-pokemon {
  background: radial-gradient(circle at 30% 30%, rgba(255, 250, 120, 0.9), rgba(220, 70, 70, 0.65));
}
.avatar-bg-capybara {
  background: radial-gradient(circle at 30% 30%, rgba(190, 160, 120, 0.9), rgba(70, 40, 20, 0.65));
}
.avatar-bg-alien {
  background: radial-gradient(circle at 30% 30%, rgba(140, 255, 180, 0.9), rgba(40, 120, 90, 0.65));
}

.sparkle {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(255,255,255,0.95), rgba(255,255,255,0));
  animation: pulse 1.2s ease-out forwards;
}

@keyframes bob {
  0% { transform: translate(-50%, -50%) translateY(0px) }
  50% { transform: translate(-50%, -50%) translateY(-4px) }
  100% { transform: translate(-50%, -50%) translateY(0px) }
}
@keyframes idle {
  0% { transform: translate(-50%, -50%) scale(1) }
  50% { transform: translate(-50%, -50%) scale(1.03) }
  100% { transform: translate(-50%, -50%) scale(1) }
}
@keyframes pulse {
  0% { transform: scale(0.8); opacity: 0.9; }
  100% { transform: scale(1.8); opacity: 0; }
}
@keyframes floatUp {
  0% { transform: translate(-50%, -50%) translateY(0px); opacity: 0.95; }
  100% { transform: translate(-50%, -50%) translateY(-70px); opacity: 0; }
}

.pet-bars-stack {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  z-index: 3;
  pointer-events: none;
  min-width: 92px;
  max-width: 148px;
}

.encounter-progress-wrap {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.encounter-progress-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: rgba(255, 255, 255, 0.96);
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.75);
  white-space: nowrap;
}
.encounter-progress-track {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.38);
  border: 1px solid rgba(255, 255, 255, 0.22);
  overflow: hidden;
}
.encounter-progress-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.08s linear;
}
.encounter-progress-wrap--play .encounter-progress-fill {
  background: linear-gradient(90deg, rgba(90, 220, 160, 0.98), rgba(180, 255, 210, 0.95));
}
.encounter-progress-wrap--fight .encounter-progress-fill {
  background: linear-gradient(90deg, rgba(255, 120, 90, 0.98), rgba(255, 200, 140, 0.95));
}

.diamond-progress-wrap {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.diamond-progress-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: rgba(255, 255, 255, 0.94);
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.75);
  white-space: nowrap;
}
.diamond-progress-track {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.38);
  border: 1px solid rgba(255, 255, 255, 0.22);
  overflow: hidden;
}
.diamond-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(126, 166, 255, 0.95), rgba(200, 230, 255, 0.95));
  transition: width 0.08s linear;
}

.diamond-flight-img {
  position: fixed;
  width: 42px;
  height: 26px;
  z-index: 10050;
  pointer-events: none;
  transform: translate(-50%, -50%);
  animation: tamagochiDiamondFlight 0.85s cubic-bezier(0.22, 0.82, 0.28, 1) forwards;
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.45));
}
@keyframes tamagochiDiamondFlight {
  from {
    transform: translate(-50%, -50%) translate(0, 0) scale(1);
    opacity: 1;
  }
  to {
    transform: translate(-50%, -50%) translate(var(--dx), var(--dy)) scale(0.55);
    opacity: 0.92;
  }
}

.map-food {
  pointer-events: none;
  z-index: 2;
}
.map-food-img {
  width: 40px;
  height: 40px;
  object-fit: contain;
  filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.45));
}

.pet-avatar {
  width: 44px;
  height: 44px;
  display: block;
  object-fit: cover;
}
</style>

