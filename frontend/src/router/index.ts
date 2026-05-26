import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import LoginView from '../views/LoginView.vue'
import GamesHubView from '../views/GamesHubView.vue'
import MessengerView from '../views/MessengerView.vue'
import AdminView from '../views/AdminView.vue'
import AdminSuspiciousView from '../views/AdminSuspiciousView.vue'
import DatabaseView from '../views/DatabaseView.vue'
import MenuView from '../games/pro-racing/MenuView.vue'
import GameView from '../games/pro-racing/GameView.vue'
import StoreView from '../games/pro-racing/StoreView.vue'
import LeaderboardView from '../games/pro-racing/LeaderboardView.vue'
import RpsHubView from '../games/rps/RpsHubView.vue'
import TamagochiWorldView from '../games/tamagochi/TamagochiWorldView.vue'
import TeamTerritoryView from '../views/TeamTerritoryView.vue'
import Minecraft2DOnlineView from '../views/Minecraft2DOnlineView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: LoginView },
    { path: '/games', component: GamesHubView },
    { path: '/messenger', component: MessengerView },
    { path: '/admin', component: AdminView },
    { path: '/admin/suspicious', component: AdminSuspiciousView },
    { path: '/database', component: DatabaseView },
    { path: '/menu', component: MenuView },
    { path: '/game/:mode', component: GameView },
    { path: '/rps', component: RpsHubView },
    { path: '/tamagochi', component: TamagochiWorldView },
    { path: '/games/team-territory', component: TeamTerritoryView },
    { path: '/games/minecraft-2d-online', component: Minecraft2DOnlineView },
    { path: '/store', component: StoreView },
    { path: '/leaderboard', component: LeaderboardView }
  ]
})

const PUBLIC_PATHS = new Set(['/'])

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (PUBLIC_PATHS.has(to.path)) {
    return true
  }
  if (!auth.token) {
    return { path: '/', query: { redirect: to.fullPath } }
  }
  return true
})
