<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { playSfx } from '../audio/sound'
import { ApiHttpError } from '../api/client'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const error = ref('')
const blockedWarningsHistory = ref<{ text: string; created_at: string }[]>([])
/** панель после ответа code=blocked (даже если список пуст) */
const showBlockedHistoryPanel = ref(false)

const regToastMsg = ref('')
const regToastErr = ref(false)
let regToastTimer: number | null = null

function showRegToast(message: string, err = false) {
  regToastMsg.value = message
  regToastErr.value = err
  if (regToastTimer) window.clearTimeout(regToastTimer)
  regToastTimer = window.setTimeout(() => {
    regToastMsg.value = ''
    regToastTimer = null
  }, 5000)
}

function fmtWarnTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return iso.slice(0, 16)
  }
}

function formatTempBanMessage(detail: { banned_until?: string; seconds_remaining?: number }): string {
  const iso = detail.banned_until
  let end = ''
  if (iso) {
    try {
      const d = new Date(iso)
      end = d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
    } catch {
      end = String(iso)
    }
  }
  const sec = Math.max(0, Number(detail.seconds_remaining || 0))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const left = h > 0 ? `${h} ч ${m} мин` : m > 0 ? `${m} мин ${s} с` : `${s} с`
  return `Аккаунт временно заблокирован. Вход снова будет доступен: ${end || '—'}. Осталось примерно: ${left}.`
}

async function signIn() {
  try {
    playSfx('button')
    error.value = ''
    blockedWarningsHistory.value = []
    showBlockedHistoryPanel.value = false
    await auth.signIn(username.value, password.value)
    router.push(username.value.trim() === 'admindb' ? '/admin' : '/games')
  } catch (e) {
    if (e instanceof ApiHttpError && e.status === 403) {
      const raw = (e.body as { detail?: unknown })?.detail
      if (raw && typeof raw === 'object' && (raw as { code?: string }).code === 'temp_ban') {
        error.value = formatTempBanMessage(raw as { banned_until?: string; seconds_remaining?: number })
        return
      }
      if (raw && typeof raw === 'object' && (raw as { code?: string }).code === 'blocked') {
        const hist = (raw as { warnings_history?: unknown }).warnings_history
        blockedWarningsHistory.value = Array.isArray(hist)
          ? (hist as { text?: string; created_at?: string }[])
              .filter((w) => typeof w?.text === 'string')
              .map((w) => ({ text: String(w.text), created_at: String(w.created_at ?? '') }))
          : []
        showBlockedHistoryPanel.value = true
        error.value =
          'Доступ заблокирован из‑за нарушений правил (лимит предупреждений). Ниже — история уведомлений системы безопасности.'
        return
      }
      if (typeof raw === 'string' && raw === 'Account blocked') {
        blockedWarningsHistory.value = []
        showBlockedHistoryPanel.value = false
        error.value = 'Аккаунт заблокирован навсегда. Обратитесь к администратору.'
        return
      }
    }
    showBlockedHistoryPanel.value = false
    blockedWarningsHistory.value = []
    error.value = 'Ошибка входа: проверь логин и пароль'
  }
}

async function register() {
  try {
    playSfx('button')
    error.value = ''
    blockedWarningsHistory.value = []
    showBlockedHistoryPanel.value = false
    await auth.register(username.value, password.value)
    router.push('/games')
  } catch (e) {
    if (e instanceof ApiHttpError && e.status === 400) {
      const raw = (e.body as { detail?: unknown })?.detail
      if (raw && typeof raw === 'object' && (raw as { code?: string }).code === 'registration_daily_limit') {
        const msg = (raw as { message?: string }).message
        showRegToast(
          typeof msg === 'string' && msg.trim()
            ? msg
            : 'Для вас сегодня лимит новых регистраций исчерпан: не более 2 новых аккаунтов за сутки. Создать ещё один сейчас нельзя — попробуйте завтра.',
          true,
        )
        return
      }
    }
    error.value = 'Ошибка регистрации: имя занято или сервер недоступен'
  }
}

onBeforeUnmount(() => {
  if (regToastTimer) window.clearTimeout(regToastTimer)
})
</script>

<template>
  <main class="page page-login page-center login-page">
    <aside class="login-corner" aria-label="Школа программирования">
      <div class="login-school-label">
        <span class="login-school-line login-school-line--1">Programming</span>
        <span class="login-school-line login-school-line--2">with</span>
        <span class="login-school-line login-school-line--3">Egorius</span>
      </div>
      <a
        class="login-tg-link"
        href="https://t.me/Egorius96"
        target="_blank"
        rel="noopener noreferrer"
        @click="playSfx('button')"
      >
        <svg class="login-tg-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path
            fill="currentColor"
            d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"
          />
        </svg>
        Telegram
      </a>
    </aside>
    <div class="login-shell">
      <header class="login-hero">
        <h1 class="login-hero-title login-hero-brand">GAMEHUB</h1>
      </header>

      <section class="panel login-card">
        <h2 class="login-card-title">Аккаунт</h2>
        <div class="login-fields">
          <label class="login-label">
            <span>Имя пользователя</span>
            <input
              v-model="username"
              class="login-input"
              type="text"
              placeholder="например, misha"
              autocomplete="username"
              maxlength="20"
            />
          </label>
          <label class="login-label">
            <span>Пароль</span>
            <input
              v-model="password"
              class="login-input"
              type="password"
              placeholder="••••••••"
              autocomplete="current-password"
              maxlength="50"
            />
          </label>
        </div>
        <div class="login-actions">
          <button type="button" class="btn login-btn login-btn-primary" @click="signIn">Войти</button>
          <button type="button" class="btn login-btn login-btn-ghost" @click="register">Создать аккаунт</button>
        </div>
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <div
          v-if="showBlockedHistoryPanel"
          class="login-blocked-history"
          role="region"
          aria-label="История предупреждений"
        >
          <ul v-if="blockedWarningsHistory.length" class="login-blocked-list">
            <li v-for="(w, idx) in blockedWarningsHistory" :key="idx" class="login-blocked-item">
              <time class="login-blocked-time">{{ fmtWarnTime(w.created_at) }}</time>
              <span class="login-blocked-text">{{ w.text }}</span>
            </li>
          </ul>
          <p v-else class="login-blocked-empty">В истории нет сохранённых текстов предупреждений.</p>
        </div>
      </section>
    </div>
  </main>

  <Teleport to="body">
    <div
      v-if="regToastMsg"
      class="reg-toast"
      :class="{ 'reg-toast--err': regToastErr }"
      role="alert"
    >
      {{ regToastMsg }}
    </div>
  </Teleport>
</template>

<style scoped>
.login-page {
  position: relative;
  min-height: 100dvh;
  min-height: 100vh;
}

.login-corner {
  position: absolute;
  top: clamp(14px, 3.5vw, 32px);
  right: clamp(14px, 3.5vw, 32px);
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  width: min(200px, calc(100vw - 28px));
  max-width: 220px;
  text-align: center;
}

.login-school-label {
  padding: 14px 14px 16px;
  border-radius: 16px;
  background: linear-gradient(160deg, rgba(18, 28, 52, 0.72), rgba(8, 14, 32, 0.82));
  border: 1px solid rgba(120, 165, 255, 0.28);
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.login-school-line {
  display: block;
  text-align: center;
  line-height: 1.22;
  color: rgba(240, 246, 255, 0.96);
}

.login-school-line--1 {
  font-size: clamp(0.68rem, 1.9vw, 0.78rem);
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  opacity: 0.92;
}

.login-school-line--2 {
  margin-top: 2px;
  font-size: clamp(0.8rem, 2.2vw, 0.92rem);
  font-weight: 500;
  letter-spacing: 0.12em;
  color: rgba(180, 205, 255, 0.88);
}

.login-school-line--3 {
  margin-top: 4px;
  font-size: clamp(1.15rem, 3.2vw, 1.45rem);
  font-weight: 800;
  letter-spacing: 0.04em;
  background: linear-gradient(100deg, #c8e0ff 0%, #8ab8ff 45%, #e8f4ff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: 0 0 24px rgba(120, 170, 255, 0.35);
}

.login-tg-link {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-decoration: none;
  color: #eaf4ff;
  background: linear-gradient(180deg, rgba(42, 154, 214, 0.45), rgba(24, 108, 168, 0.55));
  border: 1px solid rgba(120, 200, 255, 0.45);
  box-shadow: 0 6px 20px rgba(20, 100, 160, 0.25);
  transition:
    transform 0.15s ease,
    filter 0.15s ease,
    box-shadow 0.15s ease;
}

.login-tg-link:hover {
  filter: brightness(1.08);
  box-shadow: 0 8px 26px rgba(30, 130, 200, 0.35);
}

.login-tg-link:active {
  transform: scale(0.98);
}

.login-tg-svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.95;
}

@media (max-width: 380px) {
  .login-corner {
    width: auto;
    max-width: min(180px, calc(50vw - 8px));
  }
}

.reg-toast {
  position: fixed;
  z-index: 10050;
  top: max(12px, env(safe-area-inset-top, 0px));
  right: max(12px, env(safe-area-inset-right, 0px));
  left: auto;
  max-width: min(360px, calc(100vw - 24px));
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.35;
  font-weight: 600;
  color: #0f172a;
  background: linear-gradient(180deg, #ecfdf5, #d1fae5);
  border: 1px solid rgba(16, 185, 129, 0.45);
  box-shadow:
    0 10px 40px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.65);
  pointer-events: none;
}

.reg-toast--err {
  color: #fef2f2;
  background: linear-gradient(180deg, rgba(185, 28, 28, 0.95), rgba(127, 29, 29, 0.98));
  border-color: rgba(252, 165, 165, 0.55);
}
</style>
