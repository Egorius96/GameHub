<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { playSfx, stopMusic } from '../audio/sound'

const router = useRouter()
const auth = useAuthStore()

type IncidentAccount = {
  user_id: number
  username: string
  votes_in_incident: number
  first_vote_at?: string | null
  last_vote_at?: string | null
  user_created_at?: string | null
  user_last_active_at?: string | null
}
type Incident = {
  id: string
  ip: string
  day: string
  votes: number
  distinct_accounts: number
  accounts: IncidentAccount[]
  acked?: boolean
}
const suspicious = ref<{ since: string; incidents: Incident[]; users: any[]; incident_threshold_accounts?: number } | null>(null)
const susDays = ref(7)
const susError = ref('')
const warnTextByUserId = ref<Record<string, string>>({})
/** один текст предупреждения на инцидент (ip+день) для массовой отправки */
const incidentBulkText = ref<Record<string, string>>({})
const purgeIpText = ref('')
const purgePeriod = ref<'1d' | '3d' | '1w' | '1m' | '2m' | '3m' | '1y'>('1d')
const expandedUserId = ref<number | null>(null)
const historyByUserId = ref<Record<string, any[]>>({})
const historyLoading = ref<Record<string, boolean>>({})

/** минуты для временного бана по user id */
const banMinutesFor = ref<Record<string, string>>({})
const banAnyUserId = ref('')
const banAnyMinutes = ref('1440')

const BAN_MINUTE_OPTIONS = [
  { v: '60', label: '1 час' },
  { v: '360', label: '6 часов' },
  { v: '1440', label: '1 день' },
  { v: '4320', label: '3 дня' },
  { v: '10080', label: '7 дней' },
  { v: '43200', label: '30 дней' },
]

const isAdmin = computed(() => auth.username === 'admindb' && !!auth.token)

function detailMessage(data: any): string {
  const d = data?.detail
  if (typeof d === 'string') return d
  if (d && typeof d === 'object') return JSON.stringify(d)
  return 'Ошибка'
}

watch(
  suspicious,
  (s) => {
    if (!s) return
    const next = { ...banMinutesFor.value }
    for (const u of s.users ?? []) {
      const k = String(u.id)
      if (next[k] === undefined) next[k] = '1440'
    }
    for (const inc of s.incidents ?? []) {
      for (const a of inc.accounts ?? []) {
        const k = String(a.user_id)
        if (next[k] === undefined) next[k] = '1440'
      }
    }
    banMinutesFor.value = next
  },
  { immediate: true },
)

function banStatusLine(u: { blocked?: boolean; banned_until?: string | null }): string {
  if (!u.blocked) return ''
  if (!u.banned_until) return 'Статус: блокировка без срока (навсегда).'
  try {
    const d = new Date(u.banned_until)
    return `Статус: временный бан до ${d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}.`
  } catch {
    return `Статус: временный бан до ${u.banned_until}.`
  }
}

async function loadSuspicious() {
  susError.value = ''
  try {
    const resp = await fetch(`/api/admin/suspicious?days=${encodeURIComponent(String(susDays.value))}`, {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = String(data.detail ?? 'Ошибка загрузки')
      suspicious.value = null
      return
    }
    suspicious.value = {
      since: String(data.since ?? ''),
      incidents: Array.isArray(data.incidents) ? data.incidents : [],
      users: Array.isArray(data.users) ? data.users : [],
      incident_threshold_accounts: data.incident_threshold_accounts,
    }
  } catch {
    susError.value = 'Сеть: не удалось загрузить'
    suspicious.value = null
  }
}

async function loadHistory(userId: number) {
  const key = String(userId)
  historyLoading.value = { ...historyLoading.value, [key]: true }
  try {
    const resp = await fetch(`/api/admin/warnings/${userId}`, { headers: { Authorization: `Bearer ${auth.token}` } })
    const data = (await resp.json().catch(() => ({}))) as any
    if (resp.ok && Array.isArray(data.rows)) {
      historyByUserId.value = { ...historyByUserId.value, [key]: data.rows }
    }
  } finally {
    historyLoading.value = { ...historyLoading.value, [key]: false }
  }
}

async function toggleHistory(userId: number) {
  playSfx('button')
  if (expandedUserId.value === userId) {
    expandedUserId.value = null
    return
  }
  expandedUserId.value = userId
  await loadHistory(userId)
}

async function saveMessage(userId: number) {
  playSfx('button')
  susError.value = ''
  const t = String(warnTextByUserId.value[String(userId)] ?? '').trim()
  if (!t) {
    susError.value = 'Введите текст сообщения'
    return
  }
  try {
    const resp = await fetch(`/api/admin/warn/${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ text: t }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = String(data.detail ?? 'Ошибка')
      return
    }
    warnTextByUserId.value[String(userId)] = ''
    await loadSuspicious()
    if (expandedUserId.value === userId) await loadHistory(userId)
  } catch {
    susError.value = 'Сеть'
  }
}

async function bulkWarnIncident(inc: Incident) {
  playSfx('button')
  susError.value = ''
  const t = String(incidentBulkText.value[inc.id] ?? '').trim()
  if (!t) {
    susError.value = 'Введите текст для массового предупреждения'
    return
  }
  try {
    const resp = await fetch('/api/admin/incident/bulk_warn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ ip: inc.ip, day: inc.day, text: t }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    incidentBulkText.value = { ...incidentBulkText.value, [inc.id]: '' }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function bulkIncrementIncident(inc: Incident) {
  if (
    !confirm(
      `+1 к уровню предупреждения всем участникам этого инцидента (${inc.distinct_accounts} акк.)? У кого уже 3 — пропуск; при переходе на 3 — бан и снятие лайков.`,
    )
  )
    return
  playSfx('button')
  susError.value = ''
  try {
    const resp = await fetch('/api/admin/incident/bulk_warning_increment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ ip: inc.ip, day: inc.day }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function ackIncident(inc: Incident) {
  playSfx('button')
  susError.value = ''
  try {
    const resp = await fetch('/api/admin/incident/ack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ ip: inc.ip, day: inc.day }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function incrementWarning(userId: number) {
  playSfx('button')
  susError.value = ''
  try {
    const resp = await fetch(`/api/admin/warning_increment/${userId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = String(data.detail ?? 'Ошибка')
      return
    }
    await loadSuspicious()
    if (expandedUserId.value === userId) await loadHistory(userId)
  } catch {
    susError.value = 'Сеть'
  }
}

async function blockUser(userId: number) {
  playSfx('button')
  if (!confirm('Заблокировать аккаунт и удалить его лайки?')) return
  susError.value = ''
  try {
    const resp = await fetch(`/api/admin/block/${userId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function banTempUser(userId: number) {
  playSfx('button')
  susError.value = ''
  const mins = Math.max(1, parseInt(banMinutesFor.value[String(userId)] || '60', 10) || 60)
  try {
    const resp = await fetch(`/api/admin/ban_temp/${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ minutes: mins }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function unbanUser(userId: number) {
  playSfx('button')
  susError.value = ''
  try {
    const resp = await fetch(`/api/admin/unban/${userId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function banTempById() {
  const id = parseInt(banAnyUserId.value.trim(), 10)
  if (!id || id < 1) {
    susError.value = 'Укажите числовой id пользователя'
    return
  }
  const mins = Math.max(1, parseInt(banAnyMinutes.value || '60', 10) || 60)
  playSfx('button')
  susError.value = ''
  try {
    const resp = await fetch(`/api/admin/ban_temp/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ minutes: mins }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    banAnyUserId.value = ''
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function unbanById() {
  const id = parseInt(banAnyUserId.value.trim(), 10)
  if (!id || id < 1) {
    susError.value = 'Укажите числовой id пользователя'
    return
  }
  playSfx('button')
  susError.value = ''
  try {
    const resp = await fetch(`/api/admin/unban/${id}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = detailMessage(data)
      return
    }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

async function purgeIpLikes() {
  playSfx('button')
  susError.value = ''
  const ip = purgeIpText.value.trim()
  if (!ip) {
    susError.value = 'Введите IP'
    return
  }
  try {
    const resp = await fetch('/api/admin/purge_ip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
      body: JSON.stringify({ ip, period: purgePeriod.value }),
    })
    const data = (await resp.json().catch(() => ({}))) as any
    if (!resp.ok) {
      susError.value = String(data.detail ?? 'Ошибка')
      return
    }
    await loadSuspicious()
  } catch {
    susError.value = 'Сеть'
  }
}

function goMainAdmin() {
  playSfx('button')
  router.push('/admin')
}

function logout() {
  playSfx('button')
  auth.logout()
  router.push('/')
}

function useIpForPurge(ip: string) {
  playSfx('button')
  purgeIpText.value = ip
}

function fmtShort(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return String(iso).slice(0, 16)
  }
}

onMounted(() => {
  stopMusic()
  void loadSuspicious()
})
</script>

<template>
  <main class="page page-menu sus-page">
    <section class="panel sus-shell">
      <header class="sus-header">
        <div>
          <h1 class="sus-title">Подозрительные аккаунты</h1>
          <p class="sus-sub">Лайки по IP, предупреждения, очистка голосов</p>
        </div>
        <div class="sus-header-actions">
          <button type="button" class="btn sus-btn-ghost" @click="goMainAdmin">← Админка</button>
          <button type="button" class="btn" @click="logout">Logout</button>
        </div>
      </header>

      <div v-if="!isAdmin" class="admin-alert">Нет доступа.</div>

      <template v-else>
        <div v-if="susError" class="admin-alert sus-banner-err">{{ susError }}</div>

        <div class="sus-toolbar">
          <label class="sus-field">
            <span class="sus-label">Период анализа (дней)</span>
            <input v-model.number="susDays" class="admin-input sus-input-num" type="number" min="1" max="365" />
          </label>
          <button type="button" class="btn" @click="loadSuspicious">Обновить данные</button>
        </div>

        <div v-if="suspicious" class="sus-grid">
          <section class="sus-card sus-card--wide sus-card--ban">
            <h2 class="sus-card-title">Временный бан по id</h2>
            <p class="sus-card-hint">Укажите id пользователя из таблицы gamehub_users. По окончании срока вход разблокируется автоматически.</p>
            <div class="sus-purge-row">
              <input v-model="banAnyUserId" class="admin-input sus-input-id" type="number" min="1" placeholder="id" />
              <select v-model="banAnyMinutes" class="admin-select sus-select-period">
                <option v-for="o in BAN_MINUTE_OPTIONS" :key="o.v" :value="o.v">{{ o.label }}</option>
              </select>
              <button type="button" class="btn" @click="banTempById">Забанить на срок</button>
              <button type="button" class="btn sus-btn-ghost" @click="unbanById">Снять бан</button>
            </div>
          </section>

          <section class="sus-card sus-card--accent">
            <h2 class="sus-card-title">Очистка лайков по IP</h2>
            <p class="sus-card-hint">Удаляет записи голосования с указанного IP за выбранный период.</p>
            <div class="sus-purge-row">
              <input v-model="purgeIpText" class="admin-input sus-input-ip" placeholder="IP, например 192.168.1.1" />
              <select v-model="purgePeriod" class="admin-select sus-select-period">
                <option value="1d">1 день</option>
                <option value="3d">3 дня</option>
                <option value="1w">1 неделя</option>
                <option value="1m">1 месяц</option>
                <option value="2m">2 месяца</option>
                <option value="3m">3 месяца</option>
                <option value="1y">1 год</option>
              </select>
              <button type="button" class="btn btn-danger-ghost" @click="purgeIpLikes">Удалить лайки</button>
            </div>
          </section>

          <section class="sus-card sus-card--wide">
            <h2 class="sus-card-title">Инциденты накрутки</h2>
            <p class="sus-card-hint">
              Один инцидент = один IP и календарный день голосования, когда с этого IP проголосовало не меньше
              {{ suspicious.incident_threshold_accounts ?? 4 }} разных аккаунтов. Разные дни и разные IP — отдельные
              инциденты (новые ниже в списке по дате). Счётчик неотвеченных на главной админке — за последние 7 дней;
              «Снять с неотвеченных» или массовые действия уменьшают счётчик.
            </p>
            <p v-if="suspicious.since" class="sus-meta">Период выборки с: {{ suspicious.since }}</p>
            <div v-if="!suspicious.incidents.length" class="sus-empty">За выбранный период инцидентов нет</div>
            <div v-else class="sus-incident-list">
              <details v-for="inc in suspicious.incidents" :key="inc.id" class="sus-incident">
                <summary class="sus-incident-summary">
                  <span class="sus-incident-date">{{ inc.day }}</span>
                  <code class="sus-code">{{ inc.ip }}</code>
                  <span class="sus-incident-badges">
                    <span v-if="inc.acked" class="sus-badge sus-badge--done">обработан</span>
                    <span class="sus-badge">{{ inc.distinct_accounts }} акк.</span>
                    <span class="sus-badge">{{ inc.votes }} голосов</span>
                  </span>
                </summary>
                <div class="sus-incident-body">
                  <div class="sus-incident-toolbar">
                    <button type="button" class="btn sus-btn-ghost sus-btn-tiny" @click.prevent="useIpForPurge(inc.ip)">
                      Подставить IP в очистку лайков
                    </button>
                    <button
                      v-if="!inc.acked"
                      type="button"
                      class="btn sus-btn-ghost sus-btn-tiny"
                      @click.prevent="ackIncident(inc)"
                    >
                      Снять с неотвеченных
                    </button>
                  </div>
                  <div class="sus-incident-bulk">
                    <input
                      v-model="incidentBulkText[inc.id]"
                      class="admin-input sus-incident-bulk-input"
                      placeholder="Один текст предупреждения для всех участников инцидента"
                    />
                    <button type="button" class="btn sus-btn-tiny" @click.prevent="bulkWarnIncident(inc)">
                      Текст всем
                    </button>
                    <button type="button" class="btn sus-btn-tiny sus-btn-warn" @click.prevent="bulkIncrementIncident(inc)">
                      +1 предупреждение всем
                    </button>
                  </div>
                  <div class="admin-table-wrap">
                    <table class="admin-table">
                      <thead>
                        <tr>
                          <th style="width: 72px">id</th>
                          <th>username</th>
                          <th style="width: 90px">голосов</th>
                          <th>первый голос</th>
                          <th>последний голос</th>
                          <th>регистрация</th>
                          <th>активность</th>
                          <th style="width: 200px">действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="a in inc.accounts" :key="`${inc.id}-${a.user_id}`">
                          <td>{{ a.user_id }}</td>
                          <td>{{ a.username }}</td>
                          <td>{{ a.votes_in_incident }}</td>
                          <td>{{ fmtShort(a.first_vote_at) }}</td>
                          <td>{{ fmtShort(a.last_vote_at) }}</td>
                          <td>{{ fmtShort(a.user_created_at) }}</td>
                          <td>{{ fmtShort(a.user_last_active_at) }}</td>
                          <td>
                            <div class="sus-incident-actions">
                              <select v-model="banMinutesFor[String(a.user_id)]" class="admin-select sus-select-tiny">
                                <option v-for="o in BAN_MINUTE_OPTIONS" :key="o.v" :value="o.v">{{ o.label }}</option>
                              </select>
                              <button type="button" class="btn sus-btn-tiny" @click="banTempUser(a.user_id)">Бан</button>
                              <button type="button" class="btn sus-btn-tiny sus-btn-ghost" @click="unbanUser(a.user_id)">
                                Разбан
                              </button>
                            </div>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </details>
            </div>
          </section>

          <section class="sus-card sus-card--wide">
            <h2 class="sus-card-title">Помеченные в БД как suspicious</h2>
            <p class="sus-card-hint">
              Аккаунты с флагом suspicious (модерация: текст, счётчик, бан). Список не привязан к одному инциденту —
              здесь все, кого система пометила ранее.
            </p>
            <div v-if="!suspicious.users.length" class="sus-empty">Список пуст</div>
            <div v-else class="sus-user-list">
              <article v-for="u in suspicious.users" :key="u.id" class="sus-user-card">
                <div class="sus-user-head">
                  <div>
                    <div class="sus-user-name">{{ u.username }}</div>
                    <div class="sus-user-meta">
                      id {{ u.id }} · создан {{ String(u.created_at ?? '').slice(0, 10) }} · активность
                      {{ String(u.last_active_at ?? '—').slice(0, 10) }}
                    </div>
                  </div>
                  <div class="sus-badges">
                    <span v-if="u.blocked" class="sus-badge sus-badge--bad">blocked</span>
                    <span class="sus-badge">предупреждений: {{ u.warning_count ?? 0 }}/3</span>
                  </div>
                </div>
                <p v-if="u.blocked" class="sus-ban-line">{{ banStatusLine(u) }}</p>
                <div class="sus-ban-row">
                  <select v-model="banMinutesFor[String(u.id)]" class="admin-select sus-select-ban">
                    <option v-for="o in BAN_MINUTE_OPTIONS" :key="o.v" :value="o.v">{{ o.label }}</option>
                  </select>
                  <button type="button" class="btn" :disabled="u.blocked" @click="banTempUser(u.id)">Временный бан</button>
                  <button type="button" class="btn sus-btn-ghost" :disabled="!u.blocked" @click="unbanUser(u.id)">Снять бан</button>
                </div>
                <div v-if="u.mod_warning_text" class="sus-current-msg">Текущее сообщение: {{ u.mod_warning_text }}</div>
                <div class="sus-user-actions">
                  <input
                    v-model="warnTextByUserId[String(u.id)]"
                    class="admin-input sus-msg-input"
                    placeholder="Текст для баннера в меню игрока"
                  />
                  <button type="button" class="btn" :disabled="u.blocked" @click="saveMessage(u.id)">Сохранить текст</button>
                  <button type="button" class="btn sus-btn-warn" :disabled="u.blocked || (u.warning_count ?? 0) >= 3" @click="incrementWarning(u.id)">
                    +1 предупреждение
                  </button>
                  <button type="button" class="btn btn-danger-ghost" :disabled="u.blocked" @click="blockUser(u.id)">Бан навсегда + удалить лайки</button>
                  <button type="button" class="btn sus-btn-ghost" @click="toggleHistory(u.id)">
                    {{ expandedUserId === u.id ? 'Скрыть историю' : 'История сообщений' }}
                  </button>
                </div>
                <div v-if="expandedUserId === u.id" class="sus-history">
                  <div v-if="historyLoading[String(u.id)]" class="sus-meta">Загрузка…</div>
                  <ul v-else-if="(historyByUserId[String(u.id)] ?? []).length" class="sus-history-list">
                    <li v-for="h in historyByUserId[String(u.id)]" :key="h.id" class="sus-history-item">
                      <time class="sus-history-time">{{ h.created_at }}</time>
                      <span>{{ h.text }}</span>
                    </li>
                  </ul>
                  <div v-else class="sus-meta">Записей нет</div>
                </div>
              </article>
            </div>
          </section>
        </div>
      </template>
    </section>
  </main>
</template>

<style scoped>
.sus-page {
  min-height: 100vh;
}
.sus-shell {
  max-width: 1100px;
  margin: 0 auto;
  padding: 20px 18px 40px;
}
.sus-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.sus-title {
  margin: 0;
  font-size: 1.55rem;
  letter-spacing: 0.02em;
}
.sus-sub {
  margin: 6px 0 0;
  opacity: 0.82;
  font-size: 14px;
}
.sus-header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.sus-btn-ghost {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.14);
}
.sus-banner-err {
  margin-bottom: 14px;
}
.sus-toolbar {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}
.sus-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sus-label {
  font-size: 12px;
  opacity: 0.8;
}
.sus-input-num {
  width: 100px;
}
.sus-grid {
  display: grid;
  gap: 16px;
}
.sus-card {
  padding: 16px 18px;
  border-radius: 14px;
  background: rgba(10, 14, 28, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.sus-card--accent {
  border-color: rgba(120, 170, 255, 0.28);
  background: linear-gradient(145deg, rgba(18, 28, 52, 0.9), rgba(10, 14, 28, 0.75));
}
.sus-card--wide {
  grid-column: 1 / -1;
}
.sus-incident-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sus-incident {
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(6, 10, 22, 0.5);
  overflow: hidden;
}
.sus-incident-summary {
  cursor: pointer;
  padding: 12px 14px;
  font-weight: 600;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  list-style: none;
}
.sus-incident-summary::-webkit-details-marker {
  display: none;
}
.sus-incident-date {
  font-variant-numeric: tabular-nums;
  min-width: 100px;
  opacity: 0.95;
}
.sus-incident-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-left: auto;
}
.sus-incident-body {
  padding: 0 12px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.sus-incident-toolbar {
  padding: 10px 0 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.sus-incident-bulk {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 0 0 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  margin-bottom: 8px;
}
.sus-incident-bulk-input {
  flex: 1 1 220px;
  min-width: 180px;
}
.sus-incident-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.sus-btn-tiny {
  padding: 6px 10px;
  font-size: 12px;
}
.sus-select-tiny {
  min-width: 100px;
  max-width: 130px;
  padding: 6px 8px;
  font-size: 12px;
}
.sus-card-title {
  margin: 0 0 8px;
  font-size: 1.05rem;
}
.sus-card-hint {
  margin: 0 0 12px;
  font-size: 13px;
  opacity: 0.78;
}
.sus-purge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.sus-input-id {
  max-width: 140px;
  min-width: 100px;
}
.sus-ban-line {
  margin: 10px 0 0;
  font-size: 13px;
  opacity: 0.88;
  line-height: 1.4;
}
.sus-ban-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}
.sus-select-ban {
  min-width: 150px;
}
.sus-card--ban {
  border-color: rgba(255, 180, 120, 0.22);
}
.sus-input-ip {
  flex: 1 1 220px;
  min-width: 180px;
}
.sus-select-period {
  min-width: 140px;
}
.sus-meta {
  font-size: 12px;
  opacity: 0.75;
  margin-bottom: 10px;
}
.sus-empty {
  padding: 14px 0;
  opacity: 0.75;
  font-size: 14px;
}
.sus-table-wrap {
  max-height: 320px;
  overflow: auto;
}
.sus-code {
  font-size: 13px;
}
.sus-user-list {
  display: grid;
  gap: 12px;
}
.sus-user-card {
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(6, 10, 22, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.sus-user-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  align-items: flex-start;
}
.sus-user-name {
  font-weight: 700;
  font-size: 1.05rem;
}
.sus-user-meta {
  font-size: 12px;
  opacity: 0.78;
  margin-top: 4px;
}
.sus-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.sus-badge {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.sus-badge--bad {
  background: rgba(220, 80, 80, 0.15);
  border-color: rgba(255, 120, 120, 0.35);
}
.sus-badge--done {
  background: rgba(80, 160, 120, 0.2);
  border-color: rgba(120, 220, 160, 0.35);
  color: rgba(200, 255, 220, 0.95);
}
.sus-current-msg {
  margin-top: 10px;
  font-size: 13px;
  opacity: 0.9;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 200, 120, 0.08);
  border: 1px solid rgba(255, 200, 120, 0.2);
}
.sus-user-actions {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.sus-msg-input {
  flex: 1 1 240px;
  min-width: 200px;
}
.sus-btn-warn {
  background: linear-gradient(180deg, #8a6230, #5c4018);
  border-color: rgba(255, 200, 120, 0.35);
}
.sus-history {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.sus-history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}
.sus-history-item {
  font-size: 13px;
  display: grid;
  gap: 2px;
}
.sus-history-time {
  font-size: 11px;
  opacity: 0.65;
}
</style>
