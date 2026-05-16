<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { playSfx, stopMusic } from '../audio/sound'
import { startPresencePing, stopPresencePing } from '../telemetry/presence'
import { MINECRAFT_2D_COMING_SOON, TEAM_TERRITORY_COMING_SOON } from '../config/features'

const router = useRouter()
const auth = useAuthStore()
const catalog = ref<Record<string, any>>({})
const presence = ref<{ online_total: number; online_users: string[]; by_game: Record<string, number> }>({
  online_total: 0,
  online_users: [],
  by_game: {},
})
let presenceTimer: number | null = null

async function reloadGamesCatalog() {
  if (!auth.token) return
  try {
    const resp = await fetch('/api/profile/games_catalog', { headers: { Authorization: `Bearer ${auth.token}` } })
    if (resp.ok) {
      const data = await resp.json()
      catalog.value = data.games ?? {}
    }
  } catch {}
}

onMounted(async () => {
  stopMusic()
  await auth.refreshProfile()
  avatarVersion.value = Date.now()
  startPresencePing(auth.token, null)
  try {
    const resp = await fetch('/api/likes/summary', { headers: { Authorization: `Bearer ${auth.token}` } })
    if (resp.ok) likes.value = await resp.json()
  } catch {
    showToast('Лайки: ошибка сети', 'error')
  }
  await reloadGamesCatalog()

  const loadPresence = async () => {
    try {
      const resp = await fetch('/api/presence/summary', { headers: { Authorization: `Bearer ${auth.token}` } })
      if (resp.ok) presence.value = await resp.json()
    } catch {}
  }
  void loadPresence()
  void loadMessengerUnread()
  messengerUnreadTimer = window.setInterval(loadMessengerUnread, 20000)
})

onBeforeUnmount(() => {
  stopPresencePing()
  if (presenceTimer) window.clearInterval(presenceTimer)
  if (messengerUnreadTimer) window.clearInterval(messengerUnreadTimer)
  messengerUnreadTimer = null
})

const diamonds = computed(() => Number((auth.otherData as any).diamonds ?? 0))
const gamesProgress = computed(() => ((auth.otherData as any).games ?? {}) as Record<string, any>)
const proRacingTime = computed(() => Number(gamesProgress.value?.misha_pro_racing_game?.playtime ?? 0))
const proRacingOnline = computed(() => Number(presence.value.by_game?.misha_pro_racing_game ?? 0))
const rpsOnline = computed(() => Number(presence.value.by_game?.rps_game ?? 0))
const tamagochiOnline = computed(() => Number(presence.value.by_game?.tamagochi_world_game ?? 0))
const tamagochiTime = computed(() => Number(gamesProgress.value?.tamagochi_world_game?.playtime ?? 0))
const teamTerritoryOnline = computed(() => Number(presence.value.by_game?.team_territory ?? 0))
const teamTerritoryTime = computed(() => Number(gamesProgress.value?.team_territory?.playtime ?? 0))
const mc2dOnline = computed(() => Number(presence.value.by_game?.minecraft_2d_online ?? 0))
const mc2dTime = computed(() => Number(gamesProgress.value?.minecraft_2d_online?.playtime ?? 0))

function hubOnlineCount(key: string): number {
  if (key === 'misha_pro_racing_game') return proRacingOnline.value
  if (key === 'rps_game') return rpsOnline.value
  if (key === 'tamagochi_world_game') return tamagochiOnline.value
  if (key === 'team_territory') return teamTerritoryOnline.value
  if (key === 'minecraft_2d_online') return mc2dOnline.value
  return 0
}

const avatarUrl = computed(() => {
  const u = (auth.otherData as any).avatar_url
  return u && String(u).length ? String(u) : ''
})

/** Статический URL аватара не меняется при замене файла — без версии браузер показывает закэшированное изображение */
const avatarVersion = ref(0)
const avatarImgSrc = computed(() => {
  const base = avatarUrl.value
  if (!base) return ''
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}v=${avatarVersion.value}`
})
const avatarInitials = computed(() => {
  const n = String(auth.username || '?').trim()
  return n.length >= 2 ? n.slice(0, 2).toUpperCase() : n.toUpperCase() || '?'
})
const avatarError = ref('')
const modWarning = computed(() => (auth.otherData as any).mod_warning as { text?: string; level?: number; until_ban?: number } | undefined)

const likes = ref<{ day: string; counts: Record<string, number>; my_vote: string | null }>({
  day: '',
  counts: {},
  my_vote: null,
})
const messengerUnread = ref(0)
let messengerUnreadTimer: number | null = null
/** Исходный файл изображения до сжатия на сервере (аватар и фото автора игры). */
const MAX_UPLOAD_IMAGE_BEFORE_COMPRESS = 5 * 1024 * 1024
type HubToast = { id: number; message: string; variant: 'info' | 'error' }
const toasts = ref<HubToast[]>([])
let toastSeq = 0

function showToast(message: string, variant: 'info' | 'error' = 'info') {
  const id = ++toastSeq
  toasts.value = [...toasts.value, { id, message, variant }]
  window.setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, 4200)
}

const openCreatorKey = ref<string | null>(null)
const creatorMediaVersion = ref(0)

function toggleCreatorPanel(gameKey: string) {
  playSfx('button')
  openCreatorKey.value = openCreatorKey.value === gameKey ? null : gameKey
}

function creatorPhotoSrc(gameKey: string): string {
  const url = catalog.value[gameKey]?.creator_avatar_url
  if (!url || !String(url).length) return ''
  const base = String(url)
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}c=${creatorMediaVersion.value}`
}

const showAuthorModal = ref(false)
const authorGameKey = ref('')
const authorPassword = ref('')
const authorMessage = ref('')
const authorModalError = ref('')
const authorSubmitting = ref(false)
const authorFileInputRef = ref<HTMLInputElement | null>(null)

function parseCreatorDetail(data: { detail?: unknown }): { code?: string; message?: string } {
  const d = data.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const o = d as { code?: string; message?: string }
    return { code: o.code, message: typeof o.message === 'string' ? o.message : undefined }
  }
  return {}
}

function openIamAuthor(gameKey: string) {
  playSfx('button')
  const meta = catalog.value[gameKey] as { author_password_configured?: boolean } | undefined
  if (!meta?.author_password_configured) {
    showToast('В переменных окружения не задан пароль автора для этой игры.', 'error')
    return
  }
  authorGameKey.value = gameKey
  authorPassword.value = ''
  authorMessage.value = String(catalog.value[gameKey]?.creator_message ?? '')
  authorModalError.value = ''
  showAuthorModal.value = true
}

function closeAuthorModal() {
  if (!authorSubmitting.value) {
    showAuthorModal.value = false
    authorPassword.value = ''
    authorModalError.value = ''
    if (authorFileInputRef.value) authorFileInputRef.value.value = ''
  }
}

async function submitAuthorBlock() {
  authorModalError.value = ''
  const pwd = authorPassword.value.trim()
  if (!pwd) {
    authorModalError.value = 'Введите пароль автора'
    return
  }
  const file = authorFileInputRef.value?.files?.[0] ?? null
  if (file && file.size > MAX_UPLOAD_IMAGE_BEFORE_COMPRESS) {
    authorModalError.value = 'Фото слишком много весит: максимум 5 МБ до сжатия на сервере.'
    return
  }
  const initialMsg = String(catalog.value[authorGameKey.value]?.creator_message ?? '')
  const msgChanged = authorMessage.value !== initialMsg
  if (!file && !msgChanged) {
    authorModalError.value = 'Измените текст или выберите фото'
    return
  }
  authorSubmitting.value = true
  try {
    const fd = new FormData()
    fd.append('game_key', authorGameKey.value)
    fd.append('password', pwd)
    if (msgChanged) {
      fd.append('message', authorMessage.value)
    }
    if (file) {
      fd.append('file', file)
    }
    const resp = await fetch('/api/game-creators/update', {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
      body: fd,
    })
    const data = (await resp.json().catch(() => ({}))) as { detail?: unknown }
    if (!resp.ok) {
      authorSubmitting.value = false
      if (resp.status === 413) {
        authorModalError.value =
          'Фото слишком много весит (лимит 5 МБ до сжатия) или на шлюзе слишком маленький лимит тела запроса — перезапустите nginx с актуальным конфигом.'
        return
      }
      const { code, message } = parseCreatorDetail(data)
      if (code === 'author_password_not_configured') {
        showToast(message || 'В переменных окружения не задан пароль автора для этой игры.', 'error')
      } else if (code === 'wrong_author_password') {
        showToast(message || 'Пароль неверный.', 'error')
      } else if (code === 'creator_file_too_large') {
        authorModalError.value = message || 'Фото слишком много весит: максимум 5 МБ до сжатия на сервере.'
      } else {
        authorModalError.value =
          typeof data.detail === 'string'
            ? data.detail
            : message || 'Не удалось сохранить'
      }
      if (code === 'author_password_not_configured') {
        closeAuthorModal()
      }
      return
    }
    showToast('Сохранено', 'info')
    creatorMediaVersion.value = Date.now()
    await reloadGamesCatalog()
    showAuthorModal.value = false
    authorPassword.value = ''
    authorModalError.value = ''
    if (authorFileInputRef.value) authorFileInputRef.value.value = ''
  } catch {
    authorModalError.value = 'Сеть: ошибка запроса'
  } finally {
    authorSubmitting.value = false
  }
}

function mapLikeErrorDetail(detail: unknown): string {
  let s = ''
  if (typeof detail === 'string') s = detail
  else if (Array.isArray(detail) && detail.length && typeof (detail[0] as { msg?: string }).msg === 'string') {
    s = (detail[0] as { msg: string }).msg
  }
  if (s === 'Already voted today') return 'Сегодня вы уже голосовали — можно лайкнуть только одну игру в день.'
  if (s === 'Account blocked') return 'Аккаунт заблокирован.'
  return s || 'Не удалось поставить лайк'
}

async function onAvatarFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (file.size > MAX_UPLOAD_IMAGE_BEFORE_COMPRESS) {
    avatarError.value = 'Фото слишком много весит: максимум 5 МБ до сжатия на сервере.'
    input.value = ''
    return
  }
  avatarError.value = ''
  playSfx('button')
  const fd = new FormData()
  fd.append('file', file)
  try {
    const resp = await fetch('/api/profile/avatar', {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
      body: fd
    })
    if (!resp.ok) {
      const d = (await resp.json().catch(() => ({}))) as { detail?: unknown }
      const det = d.detail
      avatarError.value = Array.isArray(det)
        ? String((det[0] as any)?.msg ?? det[0] ?? 'Ошибка')
        : String(det ?? 'Не удалось загрузить')
      return
    }
    const uploaded = (await resp.json()) as { avatar_url?: string }
    if (uploaded.avatar_url) {
      auth.mergeOtherData({ avatar_url: uploaded.avatar_url })
    }
    await auth.refreshProfile()
    if (uploaded.avatar_url) {
      auth.mergeOtherData({ avatar_url: uploaded.avatar_url })
    }
    avatarVersion.value = Date.now()
  } catch {
    avatarError.value = 'Сеть: не удалось загрузить'
  } finally {
    input.value = ''
  }
}

function fmtPlaytime(totalSeconds: number): string {
  const sec = Math.max(0, Number(totalSeconds || 0))
  const totalMinutes = Math.floor(sec / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  const hh = String(hours).padStart(2, '0')
  const mm = String(minutes).padStart(2, '0')
  return `${hh} часов ${mm} минут`
}

function openProRacing() {
  playSfx('button')
  router.push('/menu')
}

function openRps() {
  playSfx('button')
  router.push('/rps')
}

function openTamagochi() {
  playSfx('button')
  router.push('/tamagochi')
}

const showTeamTerritoryWipModal = ref(false)
const showMc2dWipModal = ref(false)

function openTeamTerritory() {
  playSfx('button')
  if (TEAM_TERRITORY_COMING_SOON) {
    showTeamTerritoryWipModal.value = true
    return
  }
  router.push('/games/team-territory')
}

function openMinecraft2D() {
  playSfx('button')
  if (MINECRAFT_2D_COMING_SOON) {
    showMc2dWipModal.value = true
    return
  }
  router.push('/games/minecraft-2d-online')
}

function closeTeamTerritoryWipModal() {
  showTeamTerritoryWipModal.value = false
}

function closeMc2dWipModal() {
  showMc2dWipModal.value = false
}

function openMessenger() {
  playSfx('button')
  router.push('/messenger')
}

async function loadMessengerUnread() {
  if (!auth.token || auth.username === 'admindb') {
    messengerUnread.value = 0
    return
  }
  try {
    const resp = await fetch('/api/messenger/unread-summary', { headers: { Authorization: `Bearer ${auth.token}` } })
    if (resp.ok) {
      const d = (await resp.json()) as { chats_with_unread?: number }
      messengerUnread.value = Math.max(0, Number(d.chats_with_unread ?? 0))
    }
  } catch {
    /* ignore */
  }
}

function hubGameOpenClass(key: string): string {
  if (key === 'misha_pro_racing_game') return 'hub-game-open-btn--pro'
  if (key === 'rps_game') return 'hub-game-open-btn--rps'
  if (key === 'tamagochi_world_game') return 'hub-game-open-btn--tama'
  if (key === 'team_territory') return 'hub-game-open-btn--tt'
  if (key === 'minecraft_2d_online') return 'hub-game-open-btn--mc2d'
  return ''
}

function logout() {
  playSfx('button')
  auth.logout()
  router.push('/')
}

async function likeGame(gameKey: string) {
  playSfx('button')
  try {
    const resp = await fetch('/api/likes/vote', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({ game_key: gameKey }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      showToast(mapLikeErrorDetail(data.detail), 'error')
      return
    }
    likes.value = data
  } catch {
    showToast('Сеть: не удалось поставить лайк', 'error')
  }
}

const gamesForTop = computed(() => {
  const counts = likes.value.counts ?? {}
  const list = [
    { key: 'misha_pro_racing_game', title: 'Pro Racing', open: openProRacing },
    { key: 'rps_game', title: 'Камень ножницы бумага', open: openRps },
    { key: 'tamagochi_world_game', title: 'Тамагочи World', open: openTamagochi },
    { key: 'team_territory', title: 'Team Territory', open: openTeamTerritory },
    { key: 'minecraft_2d_online', title: 'Minecraft 2D Online', open: openMinecraft2D },
  ]
  return [...list].sort((a, b) => (Number(counts[b.key] ?? 0) - Number(counts[a.key] ?? 0)) || a.key.localeCompare(b.key))
})

const showDeleteModal = ref(false)
const deletePassword = ref('')
const deleteError = ref('')
const deleteLoading = ref(false)

function openDeleteModal() {
  playSfx('button')
  deletePassword.value = ''
  deleteError.value = ''
  showDeleteModal.value = true
}

function closeDeleteModal() {
  if (!deleteLoading.value) showDeleteModal.value = false
}

function apiDetailMessage(data: { detail?: unknown }): string {
  const d = data.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d.length && typeof (d[0] as { msg?: string }).msg === 'string') {
    return (d[0] as { msg: string }).msg
  }
  return 'Не удалось удалить аккаунт'
}

async function confirmDeleteAccount() {
  deleteError.value = ''
  deleteLoading.value = true
  try {
    const resp = await fetch('/api/auth/delete-account', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({ password: deletePassword.value }),
    })
    const data = (await resp.json().catch(() => ({}))) as { detail?: unknown; message?: string }
    if (!resp.ok) {
      deleteError.value = apiDetailMessage(data)
      return
    }
    closeDeleteModal()
    auth.logout()
    router.push('/')
  } catch {
    deleteError.value = 'Сеть: ошибка запроса'
  } finally {
    deleteLoading.value = false
  }
}
</script>

<template>
  <main class="page page-menu">
    <section class="panel" style="display:flex; gap:12px; align-items:stretch;">
      <aside class="hub-aside">
        <h3 style="margin:0 0 10px 0;">Account</h3>
        <div v-if="modWarning && (modWarning.text || (modWarning.level ?? 0) > 0)" class="hub-warning">
          <div class="hub-warning-title">Система безопасности</div>
          <div v-if="modWarning.text" class="hub-warning-body">{{ modWarning.text }}</div>
          <div class="hub-warning-meta">
            Нарушений зафиксировано: {{ modWarning.level ?? 0 }} из 3.
            До автоматической блокировки осталось этапов: <b>{{ modWarning.until_ban ?? 0 }}</b>.
          </div>
        </div>
        <div class="hub-avatar-row">
          <div class="hub-avatar-wrap">
            <img v-if="avatarUrl" :key="avatarImgSrc" :src="avatarImgSrc" class="hub-avatar-img" alt="" />
            <span v-else class="hub-avatar-placeholder">{{ avatarInitials }}</span>
          </div>
          <label class="hub-avatar-upload">
            <input
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              class="visually-hidden"
              @change="onAvatarFile"
            />
            Аватар
          </label>
        </div>
        <p v-if="avatarError" class="hub-avatar-err">{{ avatarError }}</p>
        <div style="display:grid; gap:8px; margin-top:8px;">
          <div><b>Nickname</b>: {{ auth.username }}</div>
          <div><b>Diamonds</b>: {{ diamonds }}</div>
          <div><b>Online</b>: {{ presence.online_total }}</div>
        </div>
        <div v-if="presence.online_users.length" style="margin-top:10px; font-size: 13px; opacity: 0.95;">
          <div style="margin-bottom:6px;"><b>Players online</b>:</div>
          <div style="display:flex; flex-wrap: wrap; gap:6px;">
            <span v-for="u in presence.online_users" :key="u" style="padding:2px 8px; border-radius:999px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.10);">
              {{ u }}
            </span>
          </div>
        </div>
        <div style="margin-top:12px; display:grid; gap:8px;">
          <button type="button" class="btn hub-messenger-btn" @click="openMessenger">
            <svg class="hub-messenger-tg-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path
                fill="currentColor"
                d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"
              />
            </svg>
            <span>Мессенджер</span>
            <span v-if="messengerUnread > 0" class="hub-ms-badge">{{ messengerUnread }}</span>
          </button>
        </div>
        <div style="margin-top:12px; display:grid; gap:8px;">
          <button class="btn" @click="logout">Logout</button>
          <button type="button" class="btn btn-danger-ghost" @click="openDeleteModal">Удалить аккаунт</button>
        </div>
      </aside>

      <section style="flex: 1; border-radius: 14px; padding: 14px; background: rgba(10, 14, 28, 0.35); border: 1px solid rgba(255,255,255,0.12); position:relative;">
        <h3 style="margin:0 0 10px 0;">Games</h3>
        <TransitionGroup name="top-move" tag="div" class="hub-games-list">
          <div v-for="g in gamesForTop" :key="g.key" class="hub-game-card">
            <div class="hub-game-top">
              <div class="hub-game-left">
                <button
                  type="button"
                  class="btn hub-game-open-btn"
                  :class="hubGameOpenClass(g.key)"
                  @click="g.open()"
                >
                  <span class="hub-game-open-label">{{ g.title }}</span>
                </button>
                <div class="hub-game-side-actions">
                  <button
                    type="button"
                    class="btn hub-like-btn hub-side-action"
                    :disabled="!!likes.my_vote && likes.my_vote !== g.key"
                    @click="likeGame(g.key)"
                    :title="likes.my_vote ? 'Можно лайкнуть только одну игру в день' : 'Поставить лайк за игру сегодня'"
                  >
                    👍 {{ likes.counts[g.key] ?? 0 }}
                  </button>
                  <button
                    type="button"
                    class="btn hub-creator-toggle hub-side-action"
                    :title="openCreatorKey === g.key ? 'Скрыть панель создателей' : 'Создатели игры — фото и текст от автора'"
                    @click="toggleCreatorPanel(g.key)"
                  >
                    {{ openCreatorKey === g.key ? 'Скрыть' : 'Авторы' }}
                  </button>
                </div>
              </div>
              <div class="hub-game-right">
                <div class="hub-game-title">
                  {{ catalog[g.key]?.title ?? g.title }}
                  <span v-if="g.key === 'team_territory' && TEAM_TERRITORY_COMING_SOON" class="hub-game-wip-badge">В разработке</span>
                  <span v-if="g.key === 'minecraft_2d_online' && MINECRAFT_2D_COMING_SOON" class="hub-game-wip-badge">В разработке</span>
                </div>
                <div class="hub-game-meta">
                  <span style="opacity:0.85;">В сети: {{ hubOnlineCount(g.key) }}</span>
                  <span v-if="g.key === 'misha_pro_racing_game'" style="opacity:0.75;">В игре: {{ fmtPlaytime(proRacingTime) }}</span>
                  <span v-if="g.key === 'tamagochi_world_game'" style="opacity:0.75;">В игре: {{ fmtPlaytime(tamagochiTime) }}</span>
                  <span v-if="g.key === 'team_territory'" style="opacity:0.75;">В игре: {{ fmtPlaytime(teamTerritoryTime) }}</span>
                  <span v-if="g.key === 'minecraft_2d_online'" style="opacity:0.75;">В игре: {{ fmtPlaytime(mc2dTime) }}</span>
                </div>
                <div class="hub-game-desc">
                  {{ catalog[g.key]?.description ?? '' }}
                </div>
                <div v-if="likes.my_vote === g.key" class="hub-voted-badge">Ваш лайк сегодня</div>
              </div>
            </div>
            <div v-show="openCreatorKey === g.key" class="hub-creator-panel">
              <div class="hub-creator-row">
                <div class="hub-creator-avatar-wrap">
                  <img
                    v-if="creatorPhotoSrc(g.key)"
                    :key="creatorPhotoSrc(g.key)"
                    :src="creatorPhotoSrc(g.key)"
                    alt=""
                    class="hub-creator-avatar-img"
                  />
                  <span v-else class="hub-creator-avatar-ph">?</span>
                </div>
                <div class="hub-creator-text-wrap">
                  <p v-if="String(catalog[g.key]?.creator_message ?? '').trim()" class="hub-creator-text">
                    {{ catalog[g.key]?.creator_message }}
                  </p>
                  <p v-else class="hub-creator-text hub-creator-text--muted">Автор пока не добавил текст.</p>
                </div>
              </div>
              <button type="button" class="btn hub-creator-author-btn" @click="openIamAuthor(g.key)">Я автор</button>
            </div>
          </div>
        </TransitionGroup>
      </section>
    </section>

    <Teleport to="body">
      <div class="hub-toast-stack" aria-live="polite">
        <TransitionGroup name="hub-toast" tag="div" class="hub-toast-inner">
          <div
            v-for="t in toasts"
            :key="t.id"
            class="hub-toast"
            :class="t.variant === 'error' ? 'hub-toast--error' : 'hub-toast--info'"
            role="status"
          >
            {{ t.message }}
          </div>
        </TransitionGroup>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showDeleteModal" class="delete-modal-backdrop" @click.self="closeDeleteModal">
        <div class="delete-modal" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
          <h2 id="delete-modal-title" class="delete-modal-title">Удаление аккаунта</h2>
          <p class="delete-modal-text">
            Это действие необратимо: профиль и данные на сервере пользователей будут удалены. Введите пароль для подтверждения.
          </p>
          <label class="delete-modal-label">
            <span>Логин</span>
            <input type="text" class="delete-modal-input" :value="auth.username" readonly tabindex="-1" />
          </label>
          <label class="delete-modal-label">
            <span>Пароль</span>
            <input
              v-model="deletePassword"
              type="password"
              class="delete-modal-input"
              autocomplete="current-password"
              placeholder="Введите пароль"
              @keydown.enter="confirmDeleteAccount"
            />
          </label>
          <p v-if="deleteError" class="delete-modal-err">{{ deleteError }}</p>
          <div class="delete-modal-actions">
            <button type="button" class="btn btn-modal-cancel" :disabled="deleteLoading" @click="closeDeleteModal">Отмена</button>
            <button type="button" class="btn btn-modal-delete" :disabled="deleteLoading || !deletePassword.trim()" @click="confirmDeleteAccount">
              {{ deleteLoading ? 'Удаление…' : 'Удалить навсегда' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showAuthorModal" class="delete-modal-backdrop" @click.self="closeAuthorModal">
        <div class="delete-modal author-modal" role="dialog" aria-modal="true" aria-labelledby="author-modal-title">
          <h2 id="author-modal-title" class="delete-modal-title">Блок «от автора»</h2>
          <p class="delete-modal-text">
            Введите пароль из переменных окружения для этой игры. Фото при загрузке сжимается так же, как аватар аккаунта.
          </p>
          <label class="delete-modal-label">
            <span>Пароль автора</span>
            <input
              v-model="authorPassword"
              type="password"
              class="delete-modal-input"
              autocomplete="off"
              placeholder="Секретный пароль автора игры"
              @keydown.enter="submitAuthorBlock"
            />
          </label>
          <label class="delete-modal-label">
            <span>Текст от автора</span>
            <textarea
              v-model="authorMessage"
              class="delete-modal-input author-modal-textarea"
              rows="5"
              maxlength="2000"
              placeholder="До 2000 символов"
            />
          </label>
          <label class="delete-modal-label">
            <span>Фото (по желанию, до 5 МБ до сжатия)</span>
            <input
              ref="authorFileInputRef"
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              class="delete-modal-input"
            />
          </label>
          <p v-if="authorModalError" class="delete-modal-err">{{ authorModalError }}</p>
          <div class="delete-modal-actions">
            <button type="button" class="btn btn-modal-cancel" :disabled="authorSubmitting" @click="closeAuthorModal">
              Отмена
            </button>
            <button type="button" class="btn" :disabled="authorSubmitting" @click="submitAuthorBlock">
              {{ authorSubmitting ? 'Сохранение…' : 'Сохранить' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showTeamTerritoryWipModal" class="delete-modal-backdrop" @click.self="closeTeamTerritoryWipModal">
        <div class="delete-modal" role="dialog" aria-modal="true" aria-labelledby="tt-wip-title">
          <h2 id="tt-wip-title" class="delete-modal-title">Игра в разработке</h2>
          <p class="delete-modal-text">Team Territory пока недоступна.</p>
          <div class="delete-modal-actions">
            <button type="button" class="btn btn-modal-cancel" @click="closeTeamTerritoryWipModal">Понятно</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showMc2dWipModal" class="delete-modal-backdrop" @click.self="closeMc2dWipModal">
        <div class="delete-modal" role="dialog" aria-modal="true" aria-labelledby="mc2d-wip-title">
          <h2 id="mc2d-wip-title" class="delete-modal-title">Игра в разработке</h2>
          <p class="delete-modal-text">Minecraft 2D Online пока недоступна.</p>
          <div class="delete-modal-actions">
            <button type="button" class="btn btn-modal-cancel" @click="closeMc2dWipModal">Понятно</button>
          </div>
        </div>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.hub-game-wip-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-radius: 6px;
  background: rgba(255, 152, 0, 0.25);
  border: 1px solid rgba(255, 193, 7, 0.55);
  color: #ffe082;
  vertical-align: middle;
}
.hub-messenger-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
}
.hub-messenger-tg-svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.95;
}
.hub-ms-badge {
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 999px;
  background: #2eaadc;
  color: #061018;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.hub-games-list {
  display: grid;
  gap: 10px;
}
.hub-game-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hub-game-top {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  align-items: stretch;
}
.hub-game-side-actions {
  display: flex;
  flex-direction: row;
  gap: 6px;
  align-items: stretch;
}
.hub-side-action {
  flex: 1;
  min-width: 0;
  height: 38px;
  padding: 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hub-game-side-actions .hub-like-btn {
  height: 38px;
  min-height: 0;
}
.hub-game-side-actions .hub-creator-toggle {
  height: 38px;
  min-height: 0;
  border-color: rgba(130, 170, 255, 0.38);
  background: linear-gradient(180deg, rgba(52, 72, 118, 0.95), rgba(28, 40, 72, 0.98));
  color: #e8f0ff;
}
.hub-game-side-actions .hub-creator-toggle:hover {
  filter: brightness(1.06);
  border-color: rgba(160, 195, 255, 0.5);
}
.hub-creator-panel {
  padding: 14px;
  border-radius: 12px;
  background: rgba(8, 12, 24, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.12);
  display: grid;
  gap: 12px;
}
.hub-creator-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.hub-creator-avatar-wrap {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  flex-shrink: 0;
  overflow: hidden;
  border: 2px solid rgba(120, 180, 255, 0.35);
  background: rgba(255, 255, 255, 0.06);
  display: grid;
  place-items: center;
}
.hub-creator-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.hub-creator-avatar-ph {
  font-size: 28px;
  font-weight: 800;
  opacity: 0.45;
}
.hub-creator-text-wrap {
  flex: 1;
  min-width: 0;
}
.hub-creator-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}
.hub-creator-text--muted {
  opacity: 0.72;
  font-style: italic;
}
.hub-creator-author-btn {
  height: 40px;
  justify-self: start;
}
.hub-game-left {
  display: grid;
  gap: 8px;
}
/* Фоны кнопок входа в игру: /assets/hub/*.png */
.hub-game-open-btn {
  position: relative;
  overflow: hidden;
  min-height: 80px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  border-color: rgba(255, 255, 255, 0.22);
  background-color: #0a0e18;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}
.hub-game-open-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(6, 10, 22, 0.35) 0%, rgba(6, 10, 22, 0.78) 100%);
  transition: opacity 0.2s ease;
}
.hub-game-open-btn:hover::before {
  opacity: 0.88;
}
.hub-game-open-btn--pro {
  background-image: url('/assets/hub/btn_pro_racing.png');
}
.hub-game-open-btn--pro::before {
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.25) 0%, rgba(0, 0, 0, 0.72) 100%);
}
.hub-game-open-btn--rps {
  background-image: url('/assets/hub/btn_rps.png');
}
.hub-game-open-btn--rps::before {
  background: linear-gradient(180deg, rgba(8, 8, 20, 0.4) 0%, rgba(6, 8, 22, 0.82) 100%);
}
.hub-game-open-btn--tama {
  background-image: url('/assets/hub/btn_tamagochi.png');
}
.hub-game-open-btn--tama::before {
  background: linear-gradient(155deg, rgba(12, 4, 8, 0.42) 0%, rgba(8, 6, 14, 0.82) 100%);
}
.hub-game-open-btn--tt {
  background: linear-gradient(135deg, #283593 0%, #5c6bc0 45%, #00838f 100%);
}
.hub-game-open-btn--tt::before {
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.2) 0%, rgba(0, 0, 0, 0.65) 100%);
}
.hub-game-open-btn--mc2d {
  background-image: url('/assets/hub/btn_minecraft.jpg');
}
.hub-game-open-btn--mc2d::before {
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.2) 0%, rgba(0, 0, 0, 0.65) 100%);
}
.hub-game-open-label {
  position: relative;
  z-index: 1;
  font-size: clamp(13px, 2.6vw, 15px);
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: 0.02em;
  color: #f8fbff;
  text-shadow:
    0 0 1px rgba(0, 0, 0, 0.95),
    0 1px 2px rgba(0, 0, 0, 0.95),
    0 2px 12px rgba(0, 0, 0, 0.85),
    0 0 18px rgba(0, 0, 0, 0.55);
}
.hub-like-btn {
  background: linear-gradient(180deg, #3d8f6a, #276348);
  border-color: rgba(140, 220, 180, 0.45);
}
.hub-game-right {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(10, 14, 28, 0.72);
  border: 1px solid rgba(255,255,255,0.14);
}
.hub-game-title {
  font-weight: 700;
  margin-bottom: 6px;
}
.hub-game-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: baseline;
  margin-bottom: 6px;
}
.hub-game-desc {
  opacity: 0.85;
}
.hub-voted-badge {
  margin-top: 8px;
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(120,220,160,0.12);
  border: 1px solid rgba(120,220,160,0.25);
  font-size: 12px;
  opacity: 0.95;
}
.top-move-move {
  transition: transform 350ms ease;
}
.top-move-enter-active,
.top-move-leave-active {
  transition: opacity 200ms ease;
}
.top-move-enter-from,
.top-move-leave-to {
  opacity: 0;
}
.hub-warning {
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: linear-gradient(155deg, rgba(200, 95, 28, 0.26), rgba(95, 42, 12, 0.22));
  border: 1px solid rgba(255, 155, 85, 0.42);
  box-shadow: 0 6px 20px rgba(180, 70, 15, 0.18);
  color: #fff4e8;
}
.hub-warning-title {
  font-weight: 700;
  margin-bottom: 6px;
  color: #ffd4a8;
  letter-spacing: 0.02em;
}
.hub-warning-body {
  margin-bottom: 8px;
  line-height: 1.45;
  color: rgba(255, 250, 240, 0.96);
}
.hub-warning-meta {
  font-size: 12px;
  opacity: 0.9;
  line-height: 1.45;
  color: rgba(255, 245, 230, 0.92);
}
.hub-toast-stack {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 1100;
  pointer-events: none;
  max-width: min(380px, calc(100vw - 32px));
}
.hub-toast-inner {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-end;
}
.hub-toast {
  pointer-events: auto;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.35;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(10px);
}
.hub-toast--info {
  background: rgba(22, 36, 62, 0.92);
  color: #f0f4ff;
}
.hub-toast--error {
  background: rgba(48, 18, 22, 0.94);
  border-color: rgba(255, 120, 120, 0.35);
  color: #ffe8e8;
}
.hub-toast-enter-active,
.hub-toast-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.hub-toast-enter-from,
.hub-toast-leave-to {
  opacity: 0;
  transform: translateX(12px);
}
.hub-toast-move {
  transition: transform 0.22s ease;
}
.delete-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(6, 10, 22, 0.72);
  backdrop-filter: blur(10px);
}

.delete-modal {
  width: min(420px, 100%);
  padding: 22px 22px 18px;
  border-radius: 16px;
  background: linear-gradient(165deg, rgba(22, 32, 58, 0.97), rgba(12, 18, 36, 0.98));
  border: 1px solid rgba(130, 160, 255, 0.28);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.06) inset;
}

.delete-modal-title {
  margin: 0 0 10px;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.delete-modal-text {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 1.5;
  opacity: 0.88;
}

.delete-modal-label {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  opacity: 0.9;
}

.delete-modal-input {
  width: 100%;
  padding: 11px 12px;
  border-radius: 11px;
  border: 1px solid rgba(90, 118, 190, 0.45);
  background: rgba(8, 14, 28, 0.85);
  color: #f4f7ff;
  font-size: 15px;
}

.delete-modal-input:focus {
  outline: none;
  border-color: rgba(126, 166, 255, 0.65);
  box-shadow: 0 0 0 3px rgba(71, 115, 219, 0.22);
}

.delete-modal-input[readonly] {
  opacity: 0.85;
  cursor: default;
}

.author-modal-textarea {
  min-height: 120px;
  resize: vertical;
  font: inherit;
  line-height: 1.4;
}

.delete-modal-err {
  margin: 0 0 12px;
  font-size: 13px;
  color: #ff7a7a;
}

.delete-modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  flex-wrap: wrap;
  margin-top: 6px;
}

.btn-danger-ghost {
  border-color: rgba(255, 120, 120, 0.45);
  background: linear-gradient(180deg, rgba(180, 60, 70, 0.35), rgba(120, 30, 45, 0.45));
  font-weight: 600;
}

.btn-danger-ghost:hover {
  filter: brightness(1.15);
  box-shadow: 0 8px 18px rgba(200, 60, 80, 0.25);
}

.btn-modal-cancel {
  background: linear-gradient(180deg, #3a4d78, #28385c);
  border-color: rgba(140, 167, 255, 0.35);
}

.btn-modal-delete {
  border-color: rgba(255, 100, 100, 0.55);
  background: linear-gradient(180deg, #c04050, #8a2030);
}

.btn-modal-delete:disabled {
  opacity: 0.55;
}

@media (max-width: 720px) {
  .hub-game-top {
    grid-template-columns: 1fr;
  }
}
</style>

