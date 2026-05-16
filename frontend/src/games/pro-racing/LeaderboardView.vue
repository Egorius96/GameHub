<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { startPresencePing, stopPresencePing } from '../../telemetry/presence'

const auth = useAuthStore()
const router = useRouter()
const users = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  startPresencePing(auth.token, 'misha_pro_racing_game')
  loading.value = true
  try {
    const data = await apiGet<{ users: any[] }>('/leaderboard?limit=10', auth.token)
    users.value = data.users
  } catch {
    users.value = []
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => stopPresencePing())

function rowLevel(u: any) {
  return Number(u?.other_data?.games?.misha_pro_racing_game?.car_level ?? 1)
}

function rowScore(u: any) {
  return Number(u?.other_data?.games?.misha_pro_racing_game?.high_score_seconds ?? 0)
}

function medal(i: number): string {
  if (i === 0) return '🥇'
  if (i === 1) return '🥈'
  if (i === 2) return '🥉'
  return String(i + 1)
}
</script>

<template>
  <main class="page pr-page">
    <div class="pr-bg" aria-hidden="true" />
    <section class="pr-shell">
      <header class="pr-head">
        <p class="pr-kicker">Pro Racing</p>
        <h1 class="pr-title">Лидеры</h1>
        <p class="pr-sub">Топ по рекорду выживания (секунды)</p>
      </header>

      <div class="pr-table-wrap">
        <table class="pr-table" v-if="!loading && users.length">
          <thead>
            <tr>
              <th>#</th>
              <th>Игрок</th>
              <th>Уровень</th>
              <th>Секунды</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(u, idx) in users" :key="u.username" :class="{ 'pr-row--me': u.username === auth.username }">
              <td class="pr-rank">{{ medal(idx) }}</td>
              <td class="pr-name">{{ u.username }}</td>
              <td>{{ rowLevel(u) }}</td>
              <td class="pr-score">{{ rowScore(u) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="!loading" class="pr-empty">Пока нет записей</p>
        <p v-else class="pr-empty">Загрузка…</p>
      </div>

      <button type="button" class="pr-back" @click="router.push('/menu')">← В меню</button>
    </section>
  </main>
</template>

<style scoped>
.pr-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
}
.pr-bg {
  position: fixed;
  inset: 0;
  background:
    radial-gradient(ellipse 90% 60% at 80% 10%, rgba(255, 180, 100, 0.12), transparent 45%),
    linear-gradient(165deg, #0a0e1a 0%, #121a2e 55%, #0c1020 100%);
  z-index: 0;
  pointer-events: none;
}
.pr-shell {
  position: relative;
  z-index: 1;
  max-width: 560px;
  margin: 0 auto;
  padding: 24px 18px 36px;
}
.pr-kicker {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(160, 190, 255, 0.85);
}
.pr-title {
  margin: 0 0 6px;
  font-size: 1.65rem;
  font-weight: 800;
}
.pr-sub {
  margin: 0;
  font-size: 14px;
  opacity: 0.75;
}
.pr-table-wrap {
  margin-top: 20px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(10, 14, 28, 0.65);
}
.pr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.pr-table th,
.pr-table td {
  padding: 12px 14px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.pr-table th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  opacity: 0.55;
  font-weight: 700;
  background: rgba(0, 0, 0, 0.2);
}
.pr-table tr:last-child td {
  border-bottom: none;
}
.pr-rank {
  width: 52px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.pr-name {
  font-weight: 600;
}
.pr-score {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: #9edcff;
}
.pr-row--me {
  background: rgba(100, 160, 255, 0.12);
}
.pr-empty {
  margin: 0;
  padding: 28px 16px;
  text-align: center;
  opacity: 0.75;
  font-size: 15px;
}
.pr-back {
  margin-top: 20px;
  width: 100%;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.pr-back:hover {
  border-color: rgba(140, 170, 255, 0.35);
}
</style>
