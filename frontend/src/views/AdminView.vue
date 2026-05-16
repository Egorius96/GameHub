<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { playSfx, stopMusic } from '../audio/sound'

type TableName = 'gamehub_users' | 'users'

/** Системный пользователь каталога (совпадает с backend settings.catalog_username) */
const PROTECTED_GAMEHUB_USERNAME = 'gamehub_catalog'

const router = useRouter()
const auth = useAuthStore()

const tables = ref<TableName[]>(['gamehub_users', 'users'])
const activeTable = ref<TableName>('gamehub_users')
const rows = ref<any[]>([])
const error = ref('')
const loading = ref(false)
const statsDay = ref('')
const stats = ref<{ day: string | null; count: number; top: Array<{ method: string; path: string; count: number }> } | null>(null)

const banToolUserId = ref('')
const banToolMinutes = ref('1440')
const BAN_TOOL_OPTIONS = [
  { v: '60', label: '1 ч' },
  { v: '360', label: '6 ч' },
  { v: '1440', label: '1 дн' },
  { v: '4320', label: '3 дн' },
  { v: '10080', label: '7 дн' },
  { v: '43200', label: '30 дн' },
]

const newRowJson = ref(
  JSON.stringify({ username: '', password: '', project: 'GamesHub', other_data: {} }, null, 2),
)

function apiPath(table: TableName): string {
  return table === 'users' ? '/api/admin/users' : '/api/admin/gamehub_users'
}

async function loadRows() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch(apiPath(activeTable.value), {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      error.value = String(data.detail ?? 'Ошибка загрузки')
      rows.value = []
      return
    }
    rows.value = Array.isArray(data.rows) ? data.rows : []
  } catch {
    error.value = 'Сеть: не удалось загрузить'
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  error.value = ''
  try {
    const qs = statsDay.value.trim() ? `?day=${encodeURIComponent(statsDay.value.trim())}` : ''
    const resp = await fetch(`/api/admin/stats${qs}`, { headers: { Authorization: `Bearer ${auth.token}` } })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      error.value = String(data.detail ?? 'Ошибка статистики')
      stats.value = null
      return
    }
    stats.value = {
      day: data.day ?? null,
      count: Number(data.count ?? 0),
      top: Array.isArray(data.top) ? data.top : [],
    }
  } catch {
    error.value = 'Сеть: не удалось загрузить статистику'
    stats.value = null
  }
}

const isAdmin = computed(() => auth.username === 'admindb' && !!auth.token)

const unackedSuspiciousCount = ref(0)

const msUsername = ref('')
const msChats = ref<
  {
    id: number
    type: string
    title: string | null
    last_message_preview: string | null
  }[]
>([])
const msMessages = ref<any[]>([])
const msSelectedChatId = ref<number | null>(null)
const msDiamond = ref<{ total_commission_all_time: number; entries: any[] }>({
  total_commission_all_time: 0,
  entries: [],
})

async function loadMsChats() {
  if (!isAdmin.value || !auth.token) return
  const u = msUsername.value.trim()
  if (!u) {
    msChats.value = []
    return
  }
  try {
    const resp = await fetch(
      '/api/admin/messenger/chats?username=' + encodeURIComponent(u) + '&limit=100',
      { headers: { Authorization: `Bearer ${auth.token}` } },
    )
    const data = (await resp.json().catch(() => ({}))) as any
    msChats.value = Array.isArray(data.chats) ? data.chats : []
  } catch {
    msChats.value = []
  }
}

async function loadMsMessages(chatId: number) {
  if (!isAdmin.value || !auth.token) return
  msSelectedChatId.value = chatId
  try {
    const resp = await fetch(`/api/admin/messenger/chats/${chatId}/messages?limit=200`, {
      headers: { Authorization: `Bearer ${auth.token}` } },
    )
    const data = (await resp.json().catch(() => ({}))) as any
    msMessages.value = Array.isArray(data.messages) ? data.messages : []
  } catch {
    msMessages.value = []
  }
}

async function loadMsDiamond() {
  if (!isAdmin.value || !auth.token) return
  try {
    const resp = await fetch('/api/admin/messenger/diamond-ledger?limit=100', {
      headers: { Authorization: `Bearer ${auth.token}` } },
    )
    const data = (await resp.json().catch(() => ({}))) as any
    msDiamond.value = {
      total_commission_all_time: Number(data.total_commission_all_time ?? 0),
      entries: Array.isArray(data.entries) ? data.entries : [],
    }
  } catch {
    msDiamond.value = { total_commission_all_time: 0, entries: [] }
  }
}

async function loadUnackedSuspicious() {
  if (!isAdmin.value || !auth.token) {
    unackedSuspiciousCount.value = 0
    return
  }
  try {
    const resp = await fetch('/api/admin/suspicious/unacked-count?days=7', {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      unackedSuspiciousCount.value = 0
      return
    }
    unackedSuspiciousCount.value = Math.max(0, Number(data.count ?? 0))
  } catch {
    unackedSuspiciousCount.value = 0
  }
}

function openSuspiciousPage() {
  playSfx('button')
  router.push('/admin/suspicious')
}

async function applyBanTempTool() {
  playSfx('button')
  const id = parseInt(banToolUserId.value.trim(), 10)
  if (!id || id < 1) {
    error.value = 'Укажите id пользователя (gamehub_users)'
    return
  }
  const mins = Math.max(1, parseInt(banToolMinutes.value || '60', 10) || 60)
  error.value = ''
  try {
    const resp = await fetch(`/api/admin/ban_temp/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ minutes: mins }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      error.value = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data)
      return
    }
    if (activeTable.value === 'gamehub_users') await loadRows()
  } catch {
    error.value = 'Сеть'
  }
}

async function applyUnbanTool() {
  playSfx('button')
  const id = parseInt(banToolUserId.value.trim(), 10)
  if (!id || id < 1) {
    error.value = 'Укажите id пользователя'
    return
  }
  error.value = ''
  try {
    const resp = await fetch(`/api/admin/unban/${id}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      error.value = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data)
      return
    }
    if (activeTable.value === 'gamehub_users') await loadRows()
  } catch {
    error.value = 'Сеть'
  }
}

async function createRow() {
  playSfx('button')
  error.value = ''
  let payload: any = null
  try {
    payload = JSON.parse(newRowJson.value)
  } catch {
    error.value = 'JSON: ошибка в форме создания'
    return
  }
  try {
    const resp = await fetch(apiPath(activeTable.value), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify(payload),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      error.value = String(data.detail ?? 'Ошибка создания')
      return
    }
    await loadRows()
  } catch {
    error.value = 'Сеть: ошибка создания'
  }
}

async function saveRow(r: any) {
  playSfx('button')
  error.value = ''
  try {
    const resp = await fetch(`${apiPath(activeTable.value)}/${r.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify(r),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      error.value = String(data.detail ?? 'Ошибка сохранения')
      return
    }
    await loadRows()
  } catch {
    error.value = 'Сеть: ошибка сохранения'
  }
}

function isCatalogSystemRow(r: { username?: string }) {
  return activeTable.value === 'gamehub_users' && String(r.username ?? '').trim() === PROTECTED_GAMEHUB_USERNAME
}

async function deleteRow(r: any) {
  playSfx('button')
  if (isCatalogSystemRow(r)) {
    error.value = 'Запись gamehub_catalog — системная, удаление запрещено'
    return
  }
  if (!confirm(`Удалить запись id=${r.id}?`)) return
  error.value = ''
  try {
    const resp = await fetch(`${apiPath(activeTable.value)}/${r.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      error.value = String(data.detail ?? 'Ошибка удаления')
      return
    }
    await loadRows()
  } catch {
    error.value = 'Сеть: ошибка удаления'
  }
}

function logout() {
  playSfx('button')
  auth.logout()
  router.push('/')
}

onMounted(() => {
  stopMusic()
  void loadRows()
  void loadStats()
  void loadUnackedSuspicious()
  void loadMsDiamond()
})

watch(isAdmin, (v) => {
  if (v) void loadUnackedSuspicious()
  else unackedSuspiciousCount.value = 0
})
</script>

<template>
  <main class="page page-menu">
    <section class="panel" style="max-width: 1200px;">
      <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
        <div>
          <h2 style="margin:0;">Админка GameHub</h2>
          <div style="opacity:0.85; font-size:13px;">CRUD по таблицам и базовая диагностика</div>
        </div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <button type="button" class="btn admin-btn-suspicious" @click="openSuspiciousPage">
            Подозрительные аккаунты<span v-if="unackedSuspiciousCount > 0" class="admin-sus-badge">{{ unackedSuspiciousCount }}</span>
          </button>
          <button class="btn" @click="logout">Logout</button>
        </div>
      </div>

      <div v-if="!isAdmin" class="admin-alert" style="margin-top:12px;">
        Нет доступа. Войти можно только пользователем <b>admindb</b>.
      </div>

      <div v-else style="margin-top:12px; display:grid; gap:12px;">
        <div class="admin-card">
          <div class="admin-summary" style="cursor:default;">Нагрузка backend</div>
          <div class="admin-row" style="margin-top:10px;">
            <label class="admin-label">
              <span>День (YYYY-MM-DD)</span>
              <input v-model="statsDay" class="admin-input" placeholder="например, 2026-05-11" />
            </label>
            <button class="btn" @click="loadStats">Показать</button>
          </div>
          <div v-if="stats" style="margin-top:10px; display:grid; gap:10px;">
            <div style="opacity:0.9;">Запросов за день: <b>{{ stats.count }}</b> ({{ stats.day ?? '—' }})</div>
            <div v-if="stats.top.length" class="admin-table-wrap">
              <table class="admin-table">
                <thead>
                  <tr>
                    <th style="width:90px;">method</th>
                    <th>path</th>
                    <th style="width:110px;">count</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(t, idx) in stats.top" :key="idx">
                    <td>{{ t.method }}</td>
                    <td>{{ t.path }}</td>
                    <td>{{ t.count }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="admin-card">
          <div class="admin-summary" style="cursor:default;">Бан на время (gamehub_users)</div>
          <p style="margin:8px 0 0; font-size:13px; opacity:0.85;">
            По окончании срока пользователь сможет войти сам. Перманентный бан — через страницу «Подозрительные» или кнопку бана там.
          </p>
          <div class="admin-row" style="margin-top:10px;">
            <label class="admin-label">
              <span>User id</span>
              <input v-model="banToolUserId" class="admin-input" type="number" min="1" placeholder="например 5" />
            </label>
            <label class="admin-label">
              <span>Срок</span>
              <select v-model="banToolMinutes" class="admin-select">
                <option v-for="o in BAN_TOOL_OPTIONS" :key="o.v" :value="o.v">{{ o.label }}</option>
              </select>
            </label>
            <button type="button" class="btn" @click="applyBanTempTool">Временный бан</button>
            <button type="button" class="btn admin-btn-small" style="background: rgba(255,255,255,0.08)" @click="applyUnbanTool">Снять бан</button>
          </div>
        </div>

        <div class="admin-card">
          <div class="admin-summary" style="cursor:default;">Мессенджер — чаты пользователя</div>
          <div class="admin-row" style="margin-top:10px;">
            <label class="admin-label">
              <span>Username</span>
              <input v-model="msUsername" class="admin-input" placeholder="никнейм" @keydown.enter="loadMsChats" />
            </label>
            <button type="button" class="btn" @click="loadMsChats">Найти чаты</button>
          </div>
          <div v-if="msChats.length" class="admin-table-wrap" style="margin-top:10px;">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>id</th>
                  <th>type</th>
                  <th>title</th>
                  <th>preview</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in msChats" :key="c.id">
                  <td>{{ c.id }}</td>
                  <td>{{ c.type }}</td>
                  <td>{{ c.title ?? '—' }}</td>
                  <td style="max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                    {{ c.last_message_preview ?? '—' }}
                  </td>
                  <td>
                    <button type="button" class="btn admin-btn-small" @click="loadMsMessages(c.id)">Сообщения</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="msSelectedChatId != null && msMessages.length" style="margin-top:12px;">
            <div style="font-size:13px; opacity:0.9; margin-bottom:6px;">Чат #{{ msSelectedChatId }}</div>
            <div class="admin-table-wrap" style="max-height:320px; overflow:auto;">
              <table class="admin-table">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>от</th>
                    <th>kind</th>
                    <th>текст</th>
                    <th>время</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="m in msMessages" :key="m.id">
                    <td>{{ m.id }}</td>
                    <td>{{ m.sender_username }}</td>
                    <td>{{ m.kind }}</td>
                    <td style="max-width:360px; white-space:pre-wrap; word-break:break-word;">{{ m.body }}</td>
                    <td style="white-space:nowrap;">{{ m.created_at }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="admin-card">
          <div class="admin-summary" style="cursor:default;">Мессенджер — переводы алмазов</div>
          <p style="margin:8px 0 0; font-size:14px;">
            Накопленная комиссия (вся история): <b>{{ msDiamond.total_commission_all_time }}</b>
          </p>
          <button type="button" class="btn" style="margin-top:8px;" @click="loadMsDiamond">Обновить журнал</button>
          <div v-if="msDiamond.entries.length" class="admin-table-wrap" style="margin-top:10px; max-height:400px; overflow:auto;">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>время</th>
                  <th>от</th>
                  <th>кому</th>
                  <th>A</th>
                  <th>F</th>
                  <th>IP от</th>
                  <th>IP кому</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in msDiamond.entries" :key="e.id">
                  <td style="white-space:nowrap;">{{ e.created_at }}</td>
                  <td>{{ e.from_username }} ({{ e.from_user_id }})</td>
                  <td>{{ e.to_username }} ({{ e.to_user_id }})</td>
                  <td>{{ e.amount }}</td>
                  <td>{{ e.commission }}</td>
                  <td>{{ e.sender_ip ?? '—' }}</td>
                  <td>{{ e.recipient_ip ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="admin-row">
          <label class="admin-label">
            <span>Таблица</span>
            <select v-model="activeTable" class="admin-select" @change="loadRows">
              <option v-for="t in tables" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>
          <button class="btn" :disabled="loading" @click="loadRows">Обновить</button>
        </div>

        <div v-if="error" class="admin-alert">{{ error }}</div>

        <details class="admin-card" open>
          <summary class="admin-summary">Создать запись</summary>
          <div style="display:grid; gap:10px; margin-top:10px;">
            <textarea v-model="newRowJson" class="admin-textarea" rows="8"></textarea>
            <button class="btn" @click="createRow">Create</button>
          </div>
        </details>

        <div class="admin-card">
          <div class="admin-summary" style="cursor:default;">Записи</div>
          <div v-if="loading" style="opacity:0.85; padding:10px 0;">Загрузка…</div>
          <div v-else-if="!rows.length" style="opacity:0.85; padding:10px 0;">Пусто</div>
          <div v-else class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th style="width:70px;">id</th>
                  <th>username</th>
                  <th style="width:160px;">project</th>
                  <th>other_data</th>
                  <th style="width:210px;">actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="r.id">
                  <td>{{ r.id }}</td>
                  <td><input v-model="r.username" class="admin-input" /></td>
                  <td>
                    <input v-model="r.project" class="admin-input" :disabled="activeTable !== 'users' && activeTable !== 'gamehub_users'" />
                  </td>
                  <td>
                    <textarea
                      class="admin-textarea admin-textarea--small"
                      rows="4"
                      :value="JSON.stringify(r.other_data ?? {}, null, 2)"
                      @input="
                        (e) => {
                          try {
                            r.other_data = JSON.parse((e.target as HTMLTextAreaElement).value || '{}')
                          } catch {}
                        }
                      "
                    ></textarea>
                  </td>
                  <td>
                    <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
                      <button class="btn admin-btn-small" @click="saveRow(r)">Save</button>
                      <button
                        v-if="!isCatalogSystemRow(r)"
                        class="btn admin-btn-small admin-btn-danger"
                        @click="deleteRow(r)"
                      >
                        Delete
                      </button>
                      <span v-else class="admin-protected-hint" title="Системная запись каталога">не удаляется</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.admin-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.admin-label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  opacity: 0.92;
}
.admin-select {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(90, 118, 190, 0.45);
  background: rgba(8, 14, 28, 0.85);
  color: #f4f7ff;
}
.admin-card {
  border-radius: 14px;
  padding: 12px 12px;
  background: rgba(10, 14, 28, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.admin-summary {
  font-weight: 700;
  cursor: pointer;
}
.admin-alert {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 80, 80, 0.12);
  border: 1px solid rgba(255, 80, 80, 0.25);
}
.admin-textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(90, 118, 190, 0.45);
  background: rgba(8, 14, 28, 0.85);
  color: #f4f7ff;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 12px;
}
.admin-textarea--small {
  font-size: 11px;
}
.admin-input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(90, 118, 190, 0.45);
  background: rgba(8, 14, 28, 0.85);
  color: #f4f7ff;
}
.admin-table-wrap {
  overflow: auto;
  margin-top: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.admin-table th,
.admin-table td {
  padding: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  vertical-align: top;
}
.admin-btn-small {
  padding: 10px 12px;
}
.admin-btn-danger {
  border-color: rgba(255, 120, 120, 0.45);
  background: linear-gradient(180deg, rgba(180, 60, 70, 0.35), rgba(120, 30, 45, 0.45));
}
.admin-protected-hint {
  font-size: 12px;
  opacity: 0.75;
  white-space: nowrap;
}
.admin-btn-suspicious {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.admin-sus-badge {
  min-width: 1.35em;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  background: rgba(200, 110, 55, 0.35);
  border: 1px solid rgba(255, 170, 120, 0.45);
  color: #ffe8d8;
}
</style>

