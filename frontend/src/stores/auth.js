import { defineStore } from 'pinia'
import { api } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('ls_token') || null,

    user: JSON.parse(
      localStorage.getItem('ls_user') || 'null'
    ),
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,

    organizationId: (state) =>
      state.user?.organization_id || null,

    role: (state) =>
      state.user?.role || null,
  },

  actions: {
    async login(email, password) {
      const data = await api.login({
        email,
        password,
      })

      const token = data.access_token || data.token

      this.token = token
      this.user = data.user

      localStorage.setItem('ls_token', token)
      localStorage.setItem(
        'ls_user',
        JSON.stringify(this.user)
      )

      return data
    },

    async register(
      company_name,
      full_name,
      email,
      password
    ) {
      const data = await api.register({
        company_name,
        full_name,
        email,
        password,
      })

      const token = data.access_token || data.token

      this.token = token
      this.user = data.user

      localStorage.setItem('ls_token', token)
      localStorage.setItem(
        'ls_user',
        JSON.stringify(this.user)
      )

      return data
    },

    async logout() {
      try {
        api.logout()
      } catch (error) {
        console.warn('Logout failed:', error)
      }

      this.token = null
      this.user = null

      localStorage.removeItem('ls_token')
      localStorage.removeItem('ls_user')
    },
  },
})
