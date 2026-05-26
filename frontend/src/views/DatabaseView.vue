<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

type LegacyRow = {
  id: number
  username: string
  password: string
  project: string
  other_data: Record<string, unknown>
}

type EditDraft = {
  username: string
  password: string
  project: string
  other_data: string
}

const router = useRouter()
const auth = useAuthStore()

const rows = ref<LegacyRow[]>([])
const drafts = ref<Record<number, EditDraft>>({})
const loading = ref(false)
const error = ref('')
const toast = ref('')
const toastOk = ref(true)

const newUsername = ref('')
const newPassword = ref('')
const newProject = ref('')
const newOtherData = ref('{}')

const isDatabaseUser = computed(() => auth.username === 'database' && !!auth.token)
const rowCount = computed(() => rows.value.length)

let toastTimer: number | null = null

function showToast(message: string, ok = true) {
  toast.value = message
  toastOk.value = ok
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toast.value = ''
    toastTimer = null
  }, 3200)
}

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${auth.token}`, 'Content-Type': 'application/json' }
}

function draftFor(r: LegacyRow): EditDraft {
  const d = drafts.value[r.id]
  if (d) return d
  return {
    username: r.username,
    password: r.password,
    project: r.project ?? '',
    other_data: JSON.stringify(r.other_data ?? {}, null, 2),
  }
}

function syncDrafts(list: LegacyRow[]) {
  const next: Record<number, EditDraft> = {}
  for (const r of list) {
    next[r.id] = {
      username: r.username,
      password: r.password,
      project: r.project ?? '',
      other_data: JSON.stringify(r.other_data ?? {}, null, 2),
    }
  }
  drafts.value = next
}

function parseOtherData(raw: string): Record<string, unknown> {
  const v = JSON.parse(raw)
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error('invalid json')
  return v as Record<string, unknown>
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch('/api/admin/users?limit=500', { headers: authHeaders() })
    const data = (await resp.json().catch(() => ({}))) as { rows?: LegacyRow[]; detail?: string }
    if (!resp.ok) {
      error.value = String(data.detail ?? 'Ошибка загрузки')
      rows.value = []
      drafts.value = {}
      return
    }
    rows.value = Array.isArray(data.rows) ? data.rows : []
    syncDrafts(rows.value)
  } catch {
    error.value = 'Сеть: не удалось загрузить пользователей'
    rows.value = []
    drafts.value = {}
  } finally {
    loading.value = false
  }
}

async function createUser() {
  const username = newUsername.value.trim()
  const password = newPassword.value.trim()
  const project = newProject.value.trim()
  if (!username || !password || !project) {
    showToast('Заполните username, password и project', false)
    return
  }
  let other_data: Record<string, unknown>
  try {
    other_data = parseOtherData(newOtherData.value.trim() || '{}')
  } catch {
    showToast('other_data: укажите валидный JSON', false)
    return
  }
  try {
    const resp = await fetch('/api/admin/users', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ username, password, project, other_data }),
    })
    const data = (await resp.json().catch(() => ({}))) as { detail?: string }
    if (!resp.ok) {
      showToast(String(data.detail ?? 'Не удалось создать'), false)
      return
    }
    newUsername.value = ''
    newPassword.value = ''
    newProject.value = ''
    newOtherData.value = '{}'
    await loadUsers()
    showToast('Пользователь создан')
  } catch {
    showToast('Ошибка сети при создании', false)
  }
}

async function saveUser(r: LegacyRow) {
  const d = draftFor(r)
  let other_data: Record<string, unknown>
  try {
    other_data = parseOtherData(d.other_data.trim() || '{}')
  } catch {
    showToast('other_data: невалидный JSON', false)
    return
  }
  const payload = {
    username: d.username.trim(),
    password: d.password.trim(),
    project: d.project.trim(),
    other_data,
  }
  try {
    const resp = await fetch(`/api/admin/users/${r.id}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
    const data = (await resp.json().catch(() => ({}))) as { detail?: string }
    if (!resp.ok) {
      showToast(String(data.detail ?? 'Не удалось сохранить'), false)
      return
    }
    await loadUsers()
    showToast(`Запись #${r.id} сохранена`)
  } catch {
    showToast('Ошибка сети при сохранении', false)
  }
}

async function deleteUser(r: LegacyRow) {
  if (!confirm(`Удалить пользователя «${r.username}» (id ${r.id})?`)) return
  try {
    const resp = await fetch(`/api/admin/users/${r.id}`, { method: 'DELETE', headers: authHeaders() })
    if (!resp.ok) {
      const data = (await resp.json().catch(() => ({}))) as { detail?: string }
      showToast(String(data.detail ?? 'Не удалось удалить'), false)
      return
    }
    await loadUsers()
    showToast('Запись удалена')
  } catch {
    showToast('Ошибка сети при удалении', false)
  }
}

function patchDraft(id: number, field: keyof EditDraft, value: string) {
  const row = rows.value.find((x) => x.id === id)
  if (!row) return
  drafts.value = {
    ...drafts.value,
    [id]: { ...draftFor(row), [field]: value },
  }
}

function logout() {
  auth.logout()
  router.push('/')
}

onMounted(() => {
  if (!isDatabaseUser.value) {
    router.replace('/')
    return
  }
  void loadUsers()
})
</script>

<template>
  <div class="db-page">
    <div class="db-shell">
      <header class="db-topbar">
        <div class="db-brand">
          <span class="db-badge">Legacy</span>
          <div>
            <h1 class="db-title">Users Data</h1>
            <p class="db-sub">Таблица <code>users</code> — отдельно от <code>gamehub_users</code></p>
          </div>
        </div>
        <div class="db-topbar-actions">
          <span v-if="!loading" class="db-count">{{ rowCount }} записей</span>
          <button type="button" class="db-btn db-btn--ghost" :disabled="loading" @click="loadUsers">
            Обновить
          </button>
          <button type="button" class="db-btn db-btn--outline" @click="logout">Выйти</button>
        </div>
      </header>

      <p v-if="!isDatabaseUser" class="db-alert db-alert--err">
        Нет доступа. Войдите на GameHub как <strong>database</strong> / <strong>database</strong>.
      </p>

      <template v-else>
        <p v-if="error" class="db-alert db-alert--err">{{ error }}</p>

        <section class="db-card db-card--create">
          <h2 class="db-card-title">Новая запись</h2>
          <div class="db-form-grid">
            <label class="db-field">
              <span>Username</span>
              <input v-model="newUsername" class="db-control" type="text" placeholder="john_doe" autocomplete="off" />
            </label>
            <label class="db-field">
              <span>Password</span>
              <input v-model="newPassword" class="db-control" type="text" placeholder="••••••" autocomplete="off" />
            </label>
            <label class="db-field">
              <span>Project</span>
              <input v-model="newProject" class="db-control" type="text" placeholder="my_game" autocomplete="off" />
            </label>
            <label class="db-field db-field--wide">
              <span>Other data (JSON)</span>
              <input v-model="newOtherData" class="db-control db-control--mono" type="text" placeholder="{}" />
            </label>
          </div>
          <button type="button" class="db-btn db-btn--primary" @click="createUser">Создать</button>
        </section>

        <section class="db-card">
          <div class="db-card-head">
            <h2 class="db-card-title">Записи</h2>
            <p v-if="loading" class="db-hint">Загрузка…</p>
            <p v-else-if="!rows.length" class="db-hint">Список пуст</p>
          </div>

          <div v-if="rows.length" class="db-table-wrap">
            <table class="db-table">
              <thead>
                <tr>
                  <th class="col-id">ID</th>
                  <th>Username</th>
                  <th>Password</th>
                  <th>Project</th>
                  <th class="col-json">Other data</th>
                  <th class="col-actions">Действия</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="r.id">
                  <td class="col-id"><span class="db-id">{{ r.id }}</span></td>
                  <td>
                    <input
                      class="db-control"
                      :value="draftFor(r).username"
                      @input="patchDraft(r.id, 'username', ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                  <td>
                    <input
                      class="db-control"
                      :value="draftFor(r).password"
                      @input="patchDraft(r.id, 'password', ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                  <td>
                    <input
                      class="db-control"
                      :value="draftFor(r).project"
                      @input="patchDraft(r.id, 'project', ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                  <td class="col-json">
                    <textarea
                      class="db-control db-control--mono db-control--area"
                      rows="3"
                      :value="draftFor(r).other_data"
                      @input="patchDraft(r.id, 'other_data', ($event.target as HTMLTextAreaElement).value)"
                    />
                  </td>
                  <td class="col-actions">
                    <div class="db-row-actions">
                      <button type="button" class="db-btn db-btn--save" @click="saveUser(r)">Сохранить</button>
                      <button type="button" class="db-btn db-btn--danger" @click="deleteUser(r)">Удалить</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </div>

    <Teleport to="body">
      <div v-if="toast" class="db-toast" :class="{ 'db-toast--err': !toastOk }" role="status">
        {{ toast }}
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.db-page {
  --db-bg: #eef2f7;
  --db-surface: #ffffff;
  --db-border: #d8e0ea;
  --db-border-focus: #3b82f6;
  --db-text: #0f172a;
  --db-muted: #64748b;
  --db-input-bg: #ffffff;
  --db-input-bg-hover: #f8fafc;
  --db-shadow: 0 4px 24px rgba(15, 23, 42, 0.06);
  --db-radius: 12px;

  min-height: 100dvh;
  padding: clamp(16px, 3vw, 32px);
  background: linear-gradient(165deg, #e8eef5 0%, #f4f7fb 45%, #eef2f7 100%);
  color: var(--db-text);
  box-sizing: border-box;
}

.db-shell {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.db-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 20px 24px;
  background: var(--db-surface);
  border: 1px solid var(--db-border);
  border-radius: var(--db-radius);
  box-shadow: var(--db-shadow);
}

.db-brand {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.db-badge {
  flex-shrink: 0;
  margin-top: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #1d4ed8;
  background: #dbeafe;
  border-radius: 999px;
}

.db-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--db-text);
}

.db-sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--db-muted);
}

.db-sub code {
  padding: 1px 6px;
  font-size: 12px;
  background: #f1f5f9;
  border: 1px solid var(--db-border);
  border-radius: 4px;
  color: #334155;
}

.db-topbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.db-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--db-muted);
  padding: 6px 12px;
  background: #f1f5f9;
  border-radius: 8px;
}

.db-card {
  padding: 20px 24px;
  background: var(--db-surface);
  border: 1px solid var(--db-border);
  border-radius: var(--db-radius);
  box-shadow: var(--db-shadow);
}

.db-card--create {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.db-card-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}

.db-card-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--db-text);
}

.db-hint {
  margin: 0;
  font-size: 13px;
  color: var(--db-muted);
}

.db-form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 16px;
}

.db-field--wide {
  grid-column: 1 / -1;
}

.db-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.db-field > span {
  font-size: 12px;
  font-weight: 600;
  color: var(--db-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* Переопределение глобальных тёмных input из app.css */
.db-page :deep(input.db-control),
.db-page :deep(textarea.db-control) {
  width: 100%;
  margin: 0;
  padding: 9px 12px;
  font-size: 14px;
  line-height: 1.4;
  color: var(--db-text) !important;
  background: var(--db-input-bg) !important;
  border: 1px solid var(--db-border) !important;
  border-radius: 8px !important;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.04);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    background 0.15s ease;
}

.db-page :deep(textarea.db-control) {
  resize: vertical;
  min-height: 72px;
}

.db-page :deep(input.db-control:hover),
.db-page :deep(textarea.db-control:hover) {
  background: var(--db-input-bg-hover) !important;
  border-color: #b8c5d4 !important;
}

.db-page :deep(input.db-control:focus),
.db-page :deep(textarea.db-control:focus) {
  outline: none !important;
  border-color: var(--db-border-focus) !important;
  box-shadow:
    0 0 0 3px rgba(59, 130, 246, 0.18),
    inset 0 1px 2px rgba(15, 23, 42, 0.04) !important;
}

.db-page :deep(input.db-control::placeholder),
.db-page :deep(textarea.db-control::placeholder) {
  color: #94a3b8;
  opacity: 1;
}

.db-control--mono {
  font-family: ui-monospace, 'Cascadia Code', 'SF Mono', Menlo, monospace;
  font-size: 12px !important;
}

.db-table-wrap {
  overflow-x: auto;
  margin: 0 -4px;
  padding: 0 4px 4px;
}

.db-table {
  width: 100%;
  min-width: 900px;
  border-collapse: separate;
  border-spacing: 0;
}

.db-table th,
.db-table td {
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid #edf1f5;
}

.db-table th {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--db-muted);
  background: #f8fafc;
  position: sticky;
  top: 0;
  z-index: 1;
}

.db-table tbody tr:hover td {
  background: #fafbfd;
}

.db-table tbody tr:last-child td {
  border-bottom: none;
}

.col-id {
  width: 56px;
}

.col-json {
  min-width: 220px;
}

.col-actions {
  width: 1%;
  white-space: nowrap;
}

.db-id {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #475569;
  background: #f1f5f9;
  border-radius: 6px;
}

.db-row-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.db-btn {
  border: none;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.15s ease,
    transform 0.1s ease,
    box-shadow 0.15s ease;
  white-space: nowrap;
}

.db-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.db-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.db-btn--primary {
  align-self: flex-start;
  color: #fff;
  background: linear-gradient(180deg, #3b82f6, #2563eb);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35);
}

.db-btn--primary:hover:not(:disabled) {
  filter: brightness(1.05);
}

.db-btn--save {
  color: #fff;
  background: linear-gradient(180deg, #22c55e, #16a34a);
}

.db-btn--save:hover {
  filter: brightness(1.05);
}

.db-btn--danger {
  color: #fff;
  background: linear-gradient(180deg, #ef4444, #dc2626);
}

.db-btn--danger:hover {
  filter: brightness(1.05);
}

.db-btn--ghost {
  color: #334155;
  background: #f1f5f9;
  border: 1px solid var(--db-border);
}

.db-btn--ghost:hover:not(:disabled) {
  background: #e2e8f0;
}

.db-btn--outline {
  color: #1e40af;
  background: #fff;
  border: 1px solid #93c5fd;
}

.db-btn--outline:hover {
  background: #eff6ff;
}

.db-alert {
  margin: 0;
  padding: 12px 16px;
  border-radius: 10px;
  font-size: 14px;
}

.db-alert--err {
  color: #991b1b;
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.db-toast {
  position: fixed;
  z-index: 10050;
  bottom: max(20px, env(safe-area-inset-bottom, 0px));
  left: 50%;
  transform: translateX(-50%);
  max-width: min(420px, calc(100vw - 32px));
  padding: 12px 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #14532d;
  background: #ecfdf5;
  border: 1px solid #86efac;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.15);
  pointer-events: none;
}

.db-toast--err {
  color: #7f1d1d;
  background: #fef2f2;
  border-color: #fca5a5;
}

@media (max-width: 900px) {
  .db-form-grid {
    grid-template-columns: 1fr;
  }

  .db-field--wide {
    grid-column: auto;
  }

  .db-row-actions {
    flex-direction: row;
    flex-wrap: wrap;
  }
}

@media (max-width: 640px) {
  .db-topbar {
    padding: 16px;
  }

  .db-card {
    padding: 16px;
  }

  .db-brand {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
