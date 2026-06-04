import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import { i18n, setUiLocale } from './i18n'
import './styles/app.css'

const pinia = createPinia()
const app = createApp(App).use(pinia).use(router).use(i18n)

const auth = useAuthStore(pinia)
void auth.hydrate().finally(() => {
  setUiLocale(String((auth.otherData as any)?.ui_lang ?? 'en'))
  app.mount('#app')
})
