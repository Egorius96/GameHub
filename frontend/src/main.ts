import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import './styles/app.css'

const pinia = createPinia()
const app = createApp(App).use(pinia).use(router)

const auth = useAuthStore(pinia)
void auth.hydrate().finally(() => {
  app.mount('#app')
})
