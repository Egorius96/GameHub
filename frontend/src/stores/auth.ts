import { defineStore } from 'pinia'
import { apiGet, apiPost } from '../api/client'

interface AuthResp {
  access_token: string
  username: string
  other_data: Record<string, unknown>
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '',
    username: '',
    otherData: {} as Record<string, unknown>
  }),
  actions: {
    async signIn(username: string, password: string) {
      const data = await apiPost<AuthResp>('/auth/sign-in', { username, password })
      this.token = data.access_token
      this.username = data.username
      this.otherData = data.other_data
    },
    async register(username: string, password: string) {
      const data = await apiPost<AuthResp>('/auth/register', { username, password })
      this.token = data.access_token
      this.username = data.username
      this.otherData = data.other_data
    },
    async refreshProfile() {
      if (!this.token) return
      const data = await apiGet<{ username: string; other_data: Record<string, unknown> }>('/profile', this.token)
      this.username = data.username
      this.otherData = data.other_data
    },
    /** Частичное обновление профиля без потери остальных полей */
    mergeOtherData(partial: Record<string, unknown>) {
      this.otherData = { ...this.otherData, ...partial }
    },
    logout() {
      this.token = ''
      this.username = ''
      this.otherData = {}
    }
  }
})
