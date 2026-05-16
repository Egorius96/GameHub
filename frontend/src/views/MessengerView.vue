<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { playSfx, stopMusic } from '../audio/sound'
import { startPresencePing, stopPresencePing } from '../telemetry/presence'

const router = useRouter()
const auth = useAuthStore()

type ChatRow = {
  id: number
  type: string
  title: string | null
  unread_count: number
  last_message_at: string | null
  last_message_preview: string | null
  peer?: { id: number; username: string }
}

type MsgRow = {
  id: number
  seq: number
  sender_id: number
  sender_username: string
  kind: string
  body: string
  created_at: string
}

const chats = ref<ChatRow[]>([])
const messages = ref<MsgRow[]>([])
const activeChatId = ref<number | null>(null)
const composerText = ref('')
const loadingChats = ref(false)
const loadingMsgs = ref(false)
const searchQ = ref('')
const searchResults = ref<{ id: number; username: string }[]>([])
const showNewDm = ref(false)
const showCreateGroup = ref(false)
const groupTitle = ref('')
const showTransfer = ref(false)
const transferAmount = ref(3)
const transferToId = ref<number | null>(null)
const toastMsg = ref('')
const toastErr = ref(false)
let ws: WebSocket | null = null
let toastTimer: number | null = null

/** Популярные современные эмодзи для быстрой вставки в чат */
const MSG_EMOJIS = [
  '😂',
  '❤️',
  '🔥',
  '✨',
  '👍',
  '🎉',
  '🤣',
  '😍',
  '🙏',
  '💪',
  '👏',
  '🤔',
  '😊',
  '🥹',
  '🫶',
  '👀',
  '✅',
  '💯',
  '🙌',
  '⭐',
] as const

const showFriendsModal = ref(false)
const friendsList = ref<{ id: number; username: string }[]>([])
const friendsIncoming = ref<{ id: number; username: string }[]>([])
const friendsOutgoing = ref<{ id: number; username: string }[]>([])
const friendsSearchQ = ref('')
const friendsSearchResults = ref<{ id: number; username: string }[]>([])
const loadingFriends = ref(false)
const showEmojiPicker = ref(false)
const composerRef = ref<HTMLTextAreaElement | null>(null)
/** Имена пользователей «в сети» по presence (как в /api/presence/summary). */
const presenceOnlineUsers = ref<string[]>([])
let friendsPresenceTimer: number | null = null

const activeChat = computed(() => chats.value.find((c) => c.id === activeChatId.value) ?? null)
const myUserId = ref<number | null>(null)

const friendsSortedForDisplay = computed(() => {
  const online = new Set(presenceOnlineUsers.value)
  return [...friendsList.value].sort((a, b) => {
    const ao = online.has(a.username) ? 1 : 0
    const bo = online.has(b.username) ? 1 : 0
    if (bo !== ao) return bo - ao
    return a.username.localeCompare(b.username, undefined, { sensitivity: 'base' })
  })
})

function isMyMessage(m: MsgRow): boolean {
  if (myUserId.value != null && m.sender_id === myUserId.value) return true
  return m.sender_username === auth.username
}

function showToast(msg: string, err = false) {
  toastMsg.value = msg
  toastErr.value = err
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toastMsg.value = ''
    toastTimer = null
  }, 4200)
}

function commissionPreview(a: number): number {
  return Math.round(a * 0.2)
}

const transferInputInt = computed(() => Math.floor(Number(transferAmount.value) || 0))
const transferPreviewOk = computed(() => transferInputInt.value >= 3)
const transferFee = computed(() =>
  transferPreviewOk.value ? commissionPreview(transferInputInt.value) : 0,
)
const transferTotal = computed(() =>
  transferPreviewOk.value ? transferInputInt.value + transferFee.value : 0,
)

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${auth.token}` }
}

async function resolveMyUserId() {
  const resp = await fetch('/api/messenger/users/search?q=' + encodeURIComponent(auth.username), {
    headers: authHeaders(),
  })
  if (!resp.ok) return
  const data = (await resp.json()) as { users?: { id: number; username: string }[] }
  const u = (data.users ?? []).find((x) => x.username === auth.username)
  if (u) myUserId.value = u.id
}

async function loadChats() {
  loadingChats.value = true
  try {
    const resp = await fetch('/api/messenger/chats', { headers: authHeaders() })
    if (!resp.ok) return
    const data = (await resp.json()) as { chats: ChatRow[] }
    chats.value = data.chats ?? []
  } finally {
    loadingChats.value = false
  }
}

async function loadMessages(chatId: number, reset = true) {
  loadingMsgs.value = true
  try {
    const oldest = reset ? undefined : messages.value[0]?.id
    const qs = oldest ? `?before=${oldest}&limit=40` : '?limit=40'
    const resp = await fetch(`/api/messenger/chats/${chatId}/messages${qs}`, { headers: authHeaders() })
    if (!resp.ok) return
    const data = (await resp.json()) as { messages: MsgRow[] }
    const chunk = data.messages ?? []
    if (reset) messages.value = chunk
    else messages.value = [...chunk, ...messages.value]
  } finally {
    loadingMsgs.value = false
  }
}

async function openChat(c: ChatRow) {
  playSfx('button')
  activeChatId.value = c.id
  await loadMessages(c.id, true)
  await fetch(`/api/messenger/chats/${c.id}/read`, { method: 'POST', headers: authHeaders() })
  c.unread_count = 0
}

/** POST и WS оба присылают одно и то же сообщение — не дублируем по id */
function appendMessageDedupe(chatId: number, row: MsgRow) {
  if (activeChatId.value !== chatId) return
  if (messages.value.some((m) => m.id === row.id)) return
  messages.value = [...messages.value, row]
}

async function sendText() {
  const id = activeChatId.value
  const t = composerText.value.trim()
  if (!id || !t) return
  playSfx('button')
  composerText.value = ''
  const resp = await fetch(`/api/messenger/chats/${id}/messages`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: t }),
  })
  if (!resp.ok) {
    showToast('Не удалось отправить', true)
    return
  }
  const data = (await resp.json()) as { message: MsgRow }
  if (data.message) appendMessageDedupe(id, data.message)
  void loadChats()
}

async function runSearch() {
  const q = searchQ.value.trim()
  if (q.length < 1) {
    searchResults.value = []
    return
  }
  const resp = await fetch('/api/messenger/users/search?q=' + encodeURIComponent(q), { headers: authHeaders() })
  if (!resp.ok) return
  const data = (await resp.json()) as { users: { id: number; username: string }[] }
  searchResults.value = data.users ?? []
}

async function refreshFriendsPending() {
  const r2 = await fetch('/api/messenger/friends/pending', { headers: authHeaders() })
  if (!r2.ok) return
  const d = (await r2.json()) as {
    incoming?: { id: number; username: string }[]
    outgoing?: { id: number; username: string }[]
  }
  friendsIncoming.value = d.incoming ?? []
  friendsOutgoing.value = d.outgoing ?? []
}

async function refreshPresenceSummary() {
  const resp = await fetch('/api/presence/summary', { headers: authHeaders() })
  if (!resp.ok) return
  const data = (await resp.json()) as { online_users?: string[] }
  presenceOnlineUsers.value = data.online_users ?? []
}

async function loadFriendsData() {
  loadingFriends.value = true
  try {
    const [r1, r2] = await Promise.all([
      fetch('/api/messenger/friends', { headers: authHeaders() }),
      fetch('/api/messenger/friends/pending', { headers: authHeaders() }),
    ])
    if (r1.ok) {
      const d = (await r1.json()) as { friends?: { id: number; username: string }[] }
      friendsList.value = d.friends ?? []
    }
    if (r2.ok) {
      const d = (await r2.json()) as {
        incoming?: { id: number; username: string }[]
        outgoing?: { id: number; username: string }[]
      }
      friendsIncoming.value = d.incoming ?? []
      friendsOutgoing.value = d.outgoing ?? []
    }
    await refreshPresenceSummary()
  } finally {
    loadingFriends.value = false
  }
}

async function openFriendsModal() {
  playSfx('button')
  friendsSearchQ.value = ''
  friendsSearchResults.value = []
  showFriendsModal.value = true
  await loadFriendsData()
}

async function runFriendsSearch() {
  const q = friendsSearchQ.value.trim()
  if (q.length < 1) {
    friendsSearchResults.value = []
    return
  }
  const resp = await fetch('/api/messenger/users/search?q=' + encodeURIComponent(q), { headers: authHeaders() })
  if (!resp.ok) return
  const data = (await resp.json()) as { users: { id: number; username: string }[] }
  friendsSearchResults.value = data.users ?? []
}

async function sendFriendRequest(username: string) {
  playSfx('button')
  const resp = await fetch('/api/messenger/friends/request', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
  const data = (await resp.json().catch(() => ({}))) as { status?: string; detail?: unknown }
  if (!resp.ok) {
    showToast(typeof data.detail === 'string' ? data.detail : 'Не удалось отправить заявку', true)
    return
  }
  if (data.status === 'already_friends') showToast('Уже в друзьях')
  else if (data.status === 'already_pending') showToast('Заявка уже отправлена')
  else showToast('Заявка отправлена')
  await loadFriendsData()
}

async function acceptFriend(username: string) {
  playSfx('button')
  const resp = await fetch('/api/messenger/friends/accept', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
  if (!resp.ok) {
    showToast('Не удалось принять', true)
    return
  }
  showToast('Добавлен в друзья')
  await loadFriendsData()
}

async function removeFriendOrDecline(username: string) {
  playSfx('button')
  const resp = await fetch('/api/messenger/friends/' + encodeURIComponent(username), {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!resp.ok) {
    showToast('Не удалось', true)
    return
  }
  await loadFriendsData()
}

function insertEmoji(ch: string) {
  playSfx('button')
  const el = composerRef.value
  const cur = composerText.value
  if (!el) {
    composerText.value = cur + ch
    showEmojiPicker.value = false
    return
  }
  const start = el.selectionStart ?? cur.length
  const end = el.selectionEnd ?? start
  composerText.value = cur.slice(0, start) + ch + cur.slice(end)
  showEmojiPicker.value = false
  void nextTick(() => {
    el.focus()
    const pos = start + ch.length
    el.setSelectionRange(pos, pos)
  })
}

async function startDm(peerId: number) {
  playSfx('button')
  const resp = await fetch('/api/messenger/chats/dm', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ peer_user_id: peerId }),
  })
  if (!resp.ok) {
    showToast('Не удалось открыть чат', true)
    return
  }
  const data = (await resp.json()) as { chat_id: number }
  showNewDm.value = false
  searchQ.value = ''
  searchResults.value = []
  await loadChats()
  const c = chats.value.find((x) => x.id === data.chat_id)
  if (c) await openChat(c)
  else {
    activeChatId.value = data.chat_id
    await loadMessages(data.chat_id, true)
  }
}

async function createGroup() {
  const title = groupTitle.value.trim()
  if (!title) return
  playSfx('button')
  const resp = await fetch('/api/messenger/chats/group', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, member_ids: [] }),
  })
  if (!resp.ok) {
    showToast('Не удалось создать группу', true)
    return
  }
  const data = (await resp.json()) as { chat_id: number }
  showCreateGroup.value = false
  groupTitle.value = ''
  await loadChats()
  const c = chats.value.find((x) => x.id === data.chat_id)
  if (c) await openChat(c)
}

async function leaveActive() {
  const id = activeChatId.value
  if (!id || !confirm('Выйти из этого чата?')) return
  playSfx('button')
  await fetch(`/api/messenger/chats/${id}/leave`, { method: 'POST', headers: authHeaders() })
  activeChatId.value = null
  messages.value = []
  await loadChats()
}

async function addMemberFromSearch(u: { id: number; username: string }) {
  const id = activeChatId.value
  if (!id || activeChat.value?.type !== 'group') return
  playSfx('button')
  const resp = await fetch(`/api/messenger/chats/${id}/members`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: u.id }),
  })
  if (!resp.ok) showToast('Не удалось добавить', true)
  else showToast(`Добавлен: ${u.username}`)
  searchQ.value = ''
  searchResults.value = []
}

function openTransferModal() {
  const c = activeChat.value
  if (!c || c.type !== 'dm' || !c.peer) return
  transferToId.value = c.peer.id
  showTransfer.value = true
}

async function confirmTransfer() {
  const cid = activeChatId.value
  const toId = transferToId.value
  const raw = Math.floor(Number(transferAmount.value) || 0)
  if (raw < 3) {
    showToast('Минимум 3 алмаза', true)
    return
  }
  const amount = raw
  if (!cid || !toId) return
  playSfx('button')
  const resp = await fetch('/api/messenger/transfer-diamonds', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: cid, to_user_id: toId, amount }),
  })
  const data = (await resp.json().catch(() => ({}))) as { detail?: unknown; message?: MsgRow }
  if (!resp.ok) {
    const d = data.detail as any
    if (d && typeof d === 'object' && d.code === 'same_ip') {
      showToast(String(d.message ?? 'Операция отклонена системой антимошенничества. Перевод между этими аккаунтами сейчас невозможен.'), true)
    } else if (typeof d === 'string') showToast(d, true)
    else showToast('Перевод не выполнен', true)
    return
  }
  showTransfer.value = false
  if (data.message && cid) appendMessageDedupe(cid, data.message)
  await auth.refreshProfile()
  void loadChats()
}

function connectWs() {
  if (!auth.token) return
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  ws = new WebSocket(`${proto}//${host}/ws/messenger?token=${encodeURIComponent(auth.token)}`)
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data as string) as {
        type?: string
        chat_id?: number
        message?: MsgRow
        from_username?: string
      }
      if (msg.type === 'message.new' && msg.message && msg.chat_id) {
        appendMessageDedupe(msg.chat_id, msg.message)
        if (activeChatId.value === msg.chat_id) {
          void fetch(`/api/messenger/chats/${msg.chat_id}/read`, { method: 'POST', headers: authHeaders() })
        }
        void loadChats()
      }
      if (msg.type === 'message.deleted' && msg.chat_id) void loadMessages(msg.chat_id, true)
      if (msg.type === 'chat.updated') void loadChats()
      if (msg.type === 'friend.request') {
        void refreshFriendsPending()
        if (showFriendsModal.value) void loadFriendsData()
        if (msg.from_username) showToast(`Заявка в друзья: ${msg.from_username}`)
      }
      if (msg.type === 'friend.accepted') {
        void refreshFriendsPending()
        if (showFriendsModal.value) void loadFriendsData()
      }
    } catch {
      /* ignore */
    }
  }
  ws.onclose = () => {
    ws = null
  }
}

function backHub() {
  playSfx('button')
  router.push('/games')
}

watch(showFriendsModal, (open) => {
  if (friendsPresenceTimer) {
    window.clearInterval(friendsPresenceTimer)
    friendsPresenceTimer = null
  }
  if (open) {
    void refreshPresenceSummary()
    friendsPresenceTimer = window.setInterval(() => void refreshPresenceSummary(), 12000)
  }
})

onMounted(async () => {
  stopMusic()
  await auth.refreshProfile()
  startPresencePing(auth.token, 'messenger')
  await resolveMyUserId()
  await loadChats()
  void refreshFriendsPending()
  connectWs()
})

onBeforeUnmount(() => {
  stopPresencePing()
  if (friendsPresenceTimer) {
    window.clearInterval(friendsPresenceTimer)
    friendsPresenceTimer = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
  if (toastTimer) window.clearTimeout(toastTimer)
})

function displayBody(m: MsgRow): string {
  if (m.kind === 'diamond_transfer') {
    try {
      const j = JSON.parse(m.body) as { amount?: number; commission?: number }
      return `Перевод алмазов: +${j.amount ?? '?'} (комиссия ${j.commission ?? '?'})`
    } catch {
      return m.body
    }
  }
  return m.body
}
</script>

<template>
  <main class="msg-page">
    <header class="msg-top">
      <button type="button" class="btn msg-back" @click="backHub">← Хаб</button>
      <h1 class="msg-title">Мессенджер</h1>
      <div class="msg-top-actions">
        <button type="button" class="btn msg-btn-friends" @click="openFriendsModal">
          Друзья
          <span
            v-if="friendsIncoming.length > 0"
            class="msg-friends-badge"
            :aria-label="'Новых заявок: ' + friendsIncoming.length"
          >{{ friendsIncoming.length }}</span>
        </button>
        <button type="button" class="btn" @click="showNewDm = true; searchQ = ''; searchResults = []; void runSearch()">Новый чат</button>
        <button type="button" class="btn" @click="showCreateGroup = true">Группа</button>
      </div>
    </header>

    <div class="msg-encrypt-banner" aria-hidden="true">
      <span class="msg-lock" title="">🔒</span>
      <span>Сообщения передаются по защищённому каналу.</span>
    </div>

    <div class="msg-layout">
      <aside class="msg-col msg-chats">
        <div v-if="loadingChats" class="msg-muted">Загрузка…</div>
        <button
          v-for="c in chats"
          :key="c.id"
          type="button"
          class="msg-chat-item"
          :class="{ 'msg-chat-item--active': c.id === activeChatId }"
          @click="openChat(c)"
        >
          <div class="msg-chat-title">
            {{ c.type === 'dm' ? (c.peer?.username ?? 'DM') : (c.title || 'Группа') }}
          </div>
          <div class="msg-chat-preview">{{ c.last_message_preview || '—' }}</div>
          <span v-if="c.unread_count > 0" class="msg-unread-badge">{{ c.unread_count }}</span>
        </button>
      </aside>

      <section class="msg-col msg-thread">
        <template v-if="activeChat">
          <div class="msg-thread-head">
            <div>
              <b>{{ activeChat.type === 'dm' ? activeChat.peer?.username : activeChat.title }}</b>
              <span v-if="activeChat.type === 'group'" class="msg-muted"> · группа</span>
            </div>
            <div class="msg-thread-actions">
              <button v-if="activeChat.type === 'dm'" type="button" class="btn btn-sm" @click="openTransferModal">Алмазы</button>
              <button type="button" class="btn btn-sm btn-danger-ghost" @click="leaveActive">Выйти</button>
            </div>
          </div>
          <div v-if="activeChat.type === 'group'" class="msg-add-row">
            <input v-model="searchQ" class="msg-input" placeholder="Найти пользователя…" @input="runSearch" />
            <div v-if="searchResults.length" class="msg-search-dd">
              <button
                v-for="u in searchResults"
                :key="u.id"
                type="button"
                class="msg-search-item"
                @click="addMemberFromSearch(u)"
              >
                {{ u.username }}
              </button>
            </div>
          </div>
          <div class="msg-msgs">
            <div v-for="m in messages" :key="m.id" class="msg-bubble" :class="{ 'msg-bubble--me': isMyMessage(m) }">
              <div class="msg-meta">{{ m.sender_username }} · {{ new Date(m.created_at).toLocaleString() }}</div>
              <div class="msg-body">{{ displayBody(m) }}</div>
            </div>
          </div>
          <div class="msg-composer">
            <div class="msg-composer-col">
              <div class="msg-composer-toolbar">
                <button
                  type="button"
                  class="btn btn-sm msg-emoji-btn"
                  :class="{ 'msg-emoji-btn--open': showEmojiPicker }"
                  title="Эмодзи"
                  @click="showEmojiPicker = !showEmojiPicker"
                >
                  😊
                </button>
                <div v-if="showEmojiPicker" class="msg-emoji-pop" @click.stop>
                  <button
                    v-for="em in MSG_EMOJIS"
                    :key="em"
                    type="button"
                    class="msg-emoji-cell"
                    :aria-label="'Вставить ' + em"
                    @click="insertEmoji(em)"
                  >
                    {{ em }}
                  </button>
                </div>
              </div>
              <textarea
                ref="composerRef"
                v-model="composerText"
                class="msg-textarea"
                rows="2"
                placeholder="Сообщение…"
                @keydown.enter.exact.prevent="sendText"
                @focus="showEmojiPicker = false"
              />
            </div>
            <button type="button" class="btn" :disabled="!composerText.trim()" @click="sendText">Отправить</button>
          </div>
        </template>
        <div v-else class="msg-placeholder">Выберите чат слева или создайте новый.</div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="toastMsg" class="msg-toast" :class="{ 'msg-toast--err': toastErr }">{{ toastMsg }}</div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showFriendsModal" class="msg-modal-bg" @click.self="showFriendsModal = false">
        <div class="msg-modal msg-modal--wide msg-modal--friends">
          <div class="msg-modal-friends-head">
            <h3>Друзья</h3>
            <p class="msg-muted msg-modal-friends-hint">Сначала список друзей; заявки и поиск — ниже.</p>
          </div>

          <template v-if="loadingFriends">
            <p class="msg-muted">Загрузка…</p>
          </template>
          <template v-else>
            <section class="msg-friends-primary" aria-label="Список друзей">
              <h4 class="msg-subhead msg-subhead--primary">Мои друзья</h4>
              <p v-if="!friendsList.length" class="msg-muted msg-subempty">Пока никого нет — пригласите через заявки ниже.</p>
              <div v-else class="msg-friends-scroll">
                <div v-for="u in friendsSortedForDisplay" :key="'fr' + u.id" class="msg-friend-row msg-friend-row--main">
                  <div class="msg-friend-identity">
                    <span
                      class="msg-presence-dot"
                      :class="
                        presenceOnlineUsers.includes(u.username) ? 'msg-presence-dot--on' : 'msg-presence-dot--off'
                      "
                      :title="presenceOnlineUsers.includes(u.username) ? 'В сети' : 'Не в сети'"
                      aria-hidden="true"
                    />
                    <span class="msg-friend-name">{{ u.username }}</span>
                  </div>
                  <div class="msg-friend-actions">
                    <button type="button" class="btn btn-sm" @click="startDm(u.id)">Написать</button>
                    <button type="button" class="btn btn-sm btn-danger-ghost" @click="removeFriendOrDecline(u.username)">
                      Удалить
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <details class="msg-friends-secondary">
              <summary class="msg-friends-secondary-summary">
                <span class="msg-friends-secondary-title">Заявки и добавление в друзья</span>
                <span v-if="friendsIncoming.length" class="msg-friends-badge msg-friends-badge--inline">{{
                  friendsIncoming.length
                }}</span>
              </summary>
              <div class="msg-friends-secondary-body">
                <h4 class="msg-subhead">Входящие заявки</h4>
                <div v-if="!friendsIncoming.length" class="msg-muted msg-subempty">Нет новых заявок</div>
                <div v-for="u in friendsIncoming" :key="'in' + u.id" class="msg-friend-row">
                  <span class="msg-friend-name">{{ u.username }}</span>
                  <div class="msg-friend-actions">
                    <button type="button" class="btn btn-sm" @click="acceptFriend(u.username)">Принять</button>
                    <button type="button" class="btn btn-sm btn-danger-ghost" @click="removeFriendOrDecline(u.username)">
                      Отклонить
                    </button>
                  </div>
                </div>

                <h4 class="msg-subhead">Исходящие заявки</h4>
                <div v-if="!friendsOutgoing.length" class="msg-muted msg-subempty">Нет</div>
                <div v-for="u in friendsOutgoing" :key="'out' + u.id" class="msg-friend-row">
                  <span class="msg-friend-name">{{ u.username }}</span>
                  <button type="button" class="btn btn-sm btn-danger-ghost" @click="removeFriendOrDecline(u.username)">
                    Отменить
                  </button>
                </div>

                <h4 class="msg-subhead">Поиск по нику</h4>
                <input
                  v-model="friendsSearchQ"
                  class="msg-input"
                  placeholder="Введите ник…"
                  @input="runFriendsSearch"
                />
                <div v-if="friendsSearchResults.length" class="msg-modal-list msg-modal-list--friends-search">
                  <div v-for="u in friendsSearchResults" :key="'fs' + u.id" class="msg-modal-row msg-modal-row--split">
                    <span class="msg-modal-row-main msg-modal-row-text">{{ u.username }}</span>
                    <button type="button" class="btn btn-sm msg-modal-row-side" @click="sendFriendRequest(u.username)">
                      Заявка
                    </button>
                  </div>
                </div>
              </div>
            </details>
          </template>

          <button type="button" class="btn" @click="showFriendsModal = false">Закрыть</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showNewDm" class="msg-modal-bg" @click.self="showNewDm = false">
        <div class="msg-modal">
          <h3>Новый личный чат</h3>
          <input v-model="searchQ" class="msg-input" placeholder="Никнейм…" @input="runSearch" />
          <div class="msg-modal-list">
            <div v-for="u in searchResults" :key="u.id" class="msg-modal-row msg-modal-row--split">
              <button type="button" class="msg-modal-row-main" @click="startDm(u.id)">{{ u.username }}</button>
              <button type="button" class="btn btn-sm msg-modal-row-side" @click.stop="sendFriendRequest(u.username)">
                В друзья
              </button>
            </div>
          </div>
          <button type="button" class="btn" @click="showNewDm = false">Закрыть</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showCreateGroup" class="msg-modal-bg" @click.self="showCreateGroup = false">
        <div class="msg-modal">
          <h3>Новая группа</h3>
          <input v-model="groupTitle" class="msg-input" placeholder="Название" />
          <p class="msg-muted">Участников можно добавить после создания (поиск в шапке чата).</p>
          <button type="button" class="btn" :disabled="!groupTitle.trim()" @click="createGroup">Создать</button>
          <button type="button" class="btn" @click="showCreateGroup = false">Отмена</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showTransfer" class="msg-modal-bg" @click.self="showTransfer = false">
        <div class="msg-modal">
          <h3>Перевод алмазов</h3>
          <p class="msg-muted">
            Получит друг:
            <b>{{ transferPreviewOk ? transferInputInt : '—' }}</b>
            , комиссия 20%: <b>{{ transferPreviewOk ? transferFee : '—' }}</b>, списание:
            <b>{{ transferPreviewOk ? transferTotal : '—' }}</b>
          </p>
          <p v-if="!transferPreviewOk" class="msg-muted" style="margin: 0 0 4px">Минимум 3 алмаза к получателю.</p>
          <label class="msg-label">Сумма (целое, от 3)</label>
          <input v-model.number="transferAmount" type="number" min="3" step="1" class="msg-input" />
          <div class="msg-modal-actions">
            <button type="button" class="btn" @click="confirmTransfer">Перевести</button>
            <button type="button" class="btn" @click="showTransfer = false">Отмена</button>
          </div>
        </div>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.msg-page {
  min-height: 100vh;
  background: linear-gradient(165deg, #0a0e1c 0%, #121a30 45%, #0d1224 100%);
  color: #e8ecf7;
  display: flex;
  flex-direction: column;
}
.msg-top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  flex-wrap: wrap;
}
.msg-title {
  margin: 0;
  font-size: 1.25rem;
  flex: 1;
}
.msg-top-actions {
  display: flex;
  gap: 8px;
}
.msg-encrypt-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 12px;
  opacity: 0.85;
  background: rgba(46, 170, 220, 0.08);
  border-bottom: 1px solid rgba(46, 170, 220, 0.15);
}
.msg-lock {
  font-size: 14px;
}
.msg-layout {
  display: grid;
  grid-template-columns: minmax(220px, 300px) 1fr;
  flex: 1;
  min-height: 0;
}
@media (max-width: 720px) {
  .msg-layout {
    grid-template-columns: 1fr;
  }
  .msg-chats {
    max-height: 40vh;
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
}
.msg-col {
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.msg-chats {
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  overflow: auto;
  padding: 8px;
  gap: 6px;
}
.msg-chat-item {
  position: relative;
  text-align: left;
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  cursor: pointer;
  margin-bottom: 6px;
}
.msg-chat-item--active {
  border-color: rgba(80, 180, 255, 0.45);
  background: rgba(80, 180, 255, 0.12);
}
.msg-chat-title {
  font-weight: 600;
}
.msg-chat-preview {
  font-size: 12px;
  opacity: 0.8;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.msg-unread-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #2eaadc;
  color: #061018;
  font-size: 11px;
  font-weight: 700;
  min-width: 20px;
  height: 20px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.msg-thread {
  padding: 0;
}
.msg-thread-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  gap: 8px;
}
.msg-thread-actions {
  display: flex;
  gap: 8px;
}
.btn-sm {
  font-size: 13px;
  padding: 6px 10px;
}
.msg-add-row {
  position: relative;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.msg-search-dd {
  position: absolute;
  left: 14px;
  right: 14px;
  top: 100%;
  z-index: 5;
  background: #151c2e;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  max-height: 180px;
  overflow: auto;
}
.msg-search-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.msg-search-item:hover {
  background: rgba(255, 255, 255, 0.06);
}
.msg-msgs {
  flex: 1;
  overflow: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
}
.msg-bubble {
  align-self: flex-start;
  max-width: 78%;
  padding: 9px 12px 10px;
  border-radius: 14px 14px 14px 5px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
}
.msg-bubble--me {
  align-self: flex-end;
  border-radius: 14px 14px 5px 14px;
  background: linear-gradient(165deg, rgba(86, 168, 108, 0.5) 0%, rgba(42, 118, 72, 0.45) 55%, rgba(36, 92, 58, 0.42) 100%);
  border-color: rgba(120, 210, 140, 0.38);
  color: #f0faf2;
}
.msg-bubble--me .msg-meta {
  text-align: right;
}
.msg-bubble--me .msg-body {
  text-align: left;
}
.msg-meta {
  font-size: 11px;
  opacity: 0.75;
  margin-bottom: 4px;
}
.msg-body {
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-composer {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  align-items: flex-end;
}
.msg-composer-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.msg-composer-toolbar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
}
.msg-emoji-btn {
  min-width: 40px;
}
.msg-emoji-btn--open {
  border-color: rgba(46, 170, 220, 0.5);
  background: rgba(46, 170, 220, 0.15);
}
.msg-emoji-pop {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 6px;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
  padding: 8px;
  background: #1a2238;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  z-index: 20;
  min-width: 200px;
}
.msg-emoji-cell {
  font-size: 1.35rem;
  line-height: 1.2;
  padding: 6px 4px;
  border: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  cursor: pointer;
  color: inherit;
}
.msg-emoji-cell:hover {
  background: rgba(46, 170, 220, 0.2);
}
.msg-textarea {
  flex: 1;
  resize: vertical;
  min-height: 44px;
  max-height: 160px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  padding: 8px 10px;
}
.msg-input {
  width: 100%;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  padding: 8px 10px;
  margin-bottom: 8px;
}
.msg-label {
  display: block;
  font-size: 12px;
  margin-bottom: 4px;
  opacity: 0.85;
}
.msg-placeholder {
  padding: 40px 20px;
  text-align: center;
  opacity: 0.7;
}
.msg-muted {
  opacity: 0.8;
  font-size: 13px;
}
.msg-modal-bg {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 16px;
}
.msg-modal {
  background: #151c2e;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  padding: 16px;
  max-width: 400px;
  width: 100%;
  display: grid;
  gap: 10px;
}
.msg-modal--wide {
  max-width: 440px;
  max-height: min(90vh, 640px);
  overflow-y: auto;
}
.msg-modal--friends {
  gap: 12px;
}
.msg-modal-friends-head h3 {
  margin: 0 0 4px;
}
.msg-modal-friends-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.35;
}
.msg-friends-primary {
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.msg-subhead--primary {
  margin-top: 0;
}
.msg-friends-scroll {
  max-height: min(42vh, 300px);
  overflow-y: auto;
  padding-right: 2px;
}
.msg-friend-row--main {
  align-items: flex-start;
}
.msg-friend-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.msg-friend-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.msg-presence-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.msg-presence-dot--on {
  background: #22c55e;
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.25);
}
.msg-presence-dot--off {
  background: #dc2626;
  box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.2);
  opacity: 0.92;
}
.msg-friends-secondary {
  margin-top: 4px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.2);
  padding: 0 10px 10px;
}
.msg-friends-secondary-summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 4px 10px;
  font-size: 14px;
  user-select: none;
}
.msg-friends-secondary-summary::-webkit-details-marker {
  display: none;
}
.msg-friends-secondary-title {
  font-weight: 700;
  opacity: 0.95;
}
.msg-friends-secondary-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 4px;
}
.msg-modal-list--friends-search {
  max-height: 140px;
}
.msg-btn-friends {
  position: relative;
  padding-right: 14px;
}
.msg-friends-badge {
  position: absolute;
  top: -6px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 999px;
  background: linear-gradient(180deg, #f97316, #ea580c);
  color: #0f0a06;
  font-size: 11px;
  font-weight: 800;
  line-height: 20px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}
.msg-friends-badge--inline {
  position: static;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  line-height: 1;
  vertical-align: middle;
}
.msg-modal--wide .msg-modal-list {
  max-height: 160px;
}
.msg-subhead {
  margin: 8px 0 4px;
  font-size: 0.85rem;
  font-weight: 700;
  opacity: 0.95;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.msg-subempty {
  margin: 0 0 6px;
  font-size: 12px;
}
.msg-friend-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 6px;
  font-size: 14px;
}
.msg-friend-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.msg-modal-row--split {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: default;
}
.msg-modal-row-main {
  flex: 1;
  min-width: 0;
  text-align: left;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 4px 0;
  font: inherit;
}
.msg-modal-row-text {
  cursor: default;
  padding: 4px 4px 4px 0;
}
.msg-modal-row-side {
  flex-shrink: 0;
}
.msg-modal-list {
  max-height: 200px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.msg-modal-row {
  text-align: left;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  cursor: pointer;
}
.msg-modal-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.msg-toast {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 200;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(30, 40, 70, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #e8ecf7;
  max-width: 320px;
}
.msg-toast--err {
  border-color: rgba(255, 100, 100, 0.5);
  background: rgba(60, 20, 25, 0.95);
}
</style>
