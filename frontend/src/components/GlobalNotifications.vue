<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'

type InviteNote = {
  id: string
  inviter: string
  roomId: string
  expiresAt: number
}

const auth = useAuthStore()
const router = useRouter()
const { t } = useI18n()
const notes = ref<InviteNote[]>([])
const seen = new Set<string>()
let pollTimer: number | null = null

function prune() {
  const now = Date.now()
  notes.value = notes.value.filter((n) => n.expiresAt > now)
}

async function poll() {
  if (!auth.token) return
  prune()
  try {
    const resp = await fetch('/api/notifications/pending', {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    if (!resp.ok) return
    const data = await resp.json()
    const list = Array.isArray(data.notifications) ? data.notifications : []
    for (const raw of list) {
      if (raw?.type !== 'team_territory_invite') continue
      const roomId = String(raw.room_id ?? 'default')
      const inviter = String(raw.inviter ?? '')
      const exp = Date.parse(String(raw.expires_at ?? ''))
      if (!inviter || !Number.isFinite(exp) || exp <= Date.now()) continue
      const id = `tt-invite:${roomId}:${inviter}:${exp}`
      if (seen.has(id)) continue
      seen.add(id)
      notes.value = [...notes.value, { id, inviter, roomId, expiresAt: exp }]
      window.setTimeout(() => {
        notes.value = notes.value.filter((n) => n.id !== id)
      }, Math.max(1000, exp - Date.now()))
    }
  } catch {
    /* ignore */
  }
}

function openInvite(n: InviteNote) {
  notes.value = notes.value.filter((x) => x.id !== n.id)
  void router.push({ path: '/games/team-territory', query: { room: n.roomId } })
}

function dismiss(id: string) {
  notes.value = notes.value.filter((n) => n.id !== id)
}

watch(
  () => auth.token,
  (tok) => {
    if (pollTimer) window.clearInterval(pollTimer)
    pollTimer = null
    notes.value = []
    seen.clear()
    if (!tok) return
    void poll()
    pollTimer = window.setInterval(poll, 3500)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <div v-if="notes.length" class="gh-notify-stack" aria-live="polite">
    <TransitionGroup name="gh-notify" tag="div" class="gh-notify-inner">
      <button
        v-for="n in notes"
        :key="n.id"
        type="button"
        class="gh-notify-card"
        @click="openInvite(n)"
      >
        <span class="gh-notify-icon" aria-hidden="true">🎮</span>
        <span class="gh-notify-body">
          <span class="gh-notify-title">{{ t('teamTerritory.invite.title') }}</span>
          <span class="gh-notify-sub">{{ t('teamTerritory.invite.body', { user: n.inviter }) }}</span>
        </span>
        <span
          type="button"
          class="gh-notify-close"
          :aria-label="t('common.close')"
          @click.stop="dismiss(n.id)"
        >×</span>
      </button>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.gh-notify-stack {
  position: fixed;
  top: 14px;
  right: 14px;
  z-index: 1200;
  pointer-events: none;
  max-width: min(360px, calc(100vw - 28px));
}
.gh-notify-inner {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-end;
}
.gh-notify-card {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(130, 160, 255, 0.45);
  background: linear-gradient(135deg, rgba(22, 30, 58, 0.97), rgba(12, 18, 36, 0.98));
  color: #e8ecf7;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  cursor: pointer;
  text-align: left;
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.gh-notify-card:hover {
  transform: translateY(-1px);
  border-color: rgba(160, 190, 255, 0.65);
}
.gh-notify-icon {
  font-size: 1.35rem;
  line-height: 1;
  margin-top: 2px;
}
.gh-notify-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.gh-notify-title {
  font-weight: 700;
  font-size: 0.92rem;
}
.gh-notify-sub {
  font-size: 0.82rem;
  opacity: 0.88;
  line-height: 1.35;
}
.gh-notify-close {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: inherit;
  font-size: 1.2rem;
  line-height: 1;
  cursor: pointer;
}
.gh-notify-close:hover {
  background: rgba(255, 255, 255, 0.16);
}
.gh-notify-enter-active,
.gh-notify-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.gh-notify-enter-from,
.gh-notify-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
.gh-notify-move {
  transition: transform 0.22s ease;
}
</style>
