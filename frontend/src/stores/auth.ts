import { defineStore } from 'pinia'
import { apiGet, apiPost } from '../api/client'
import { clearStoredAuth, loadStoredAuth, saveStoredAuth } from './authStorage'

interface AuthResp {
  access_token: string
  username: string
  other_data: Record<string, unknown>
}

const stored = loadStoredAuth()

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: stored?.token ?? '',
    username: stored?.username ?? '',
    otherData: (stored?.otherData ?? {}) as Record<string, unknown>,
  }),
  actions: {
    persist() {
      if (!this.token) {
        clearStoredAuth()
        return
      }
      saveStoredAuth({
        token: this.token,
        username: this.username,
        otherData: this.otherData,
      })
    },
    applySession(token: string, username: string, otherData: Record<string, unknown>) {
      this.token = token
      this.username = username
      this.otherData = otherData
      this.persist()
    },
    async signIn(username: string, password: string) {
      const data = await apiPost<AuthResp>('/auth/sign-in', { username, password })
      this.applySession(data.access_token, data.username, data.other_data)
    },
    async register(username: string, password: string) {
      const data = await apiPost<AuthResp>('/auth/register', { username, password })
      this.applySession(data.access_token, data.username, data.other_data)
    },
    async refreshProfile() {
      if (!this.token) return
      const data = await apiGet<{ username: string; other_data: Record<string, unknown> }>('/profile', this.token)
      this.username = data.username
      this.otherData = data.other_data
      this.persist()
    },
    /** Восстановить сессию после F5; при невалидном JWT — выход */
    async hydrate() {
      if (!this.token) return
      try {
        await this.refreshProfile()
      } catch {
        this.logout()
      }
    },
    mergeOtherData(partial: Record<string, unknown>) {
      this.otherData = { ...this.otherData, ...partial }
      this.persist()
    },
    logout() {
      this.token = ''
      this.username = ''
      this.otherData = {}
      clearStoredAuth()
    },
  },
})
