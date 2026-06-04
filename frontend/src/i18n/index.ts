import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import ru from './locales/ru.json'
import it from './locales/it.json'
import es from './locales/es.json'
import de from './locales/de.json'

export type UiLang = 'en' | 'ru' | 'it' | 'es' | 'de'

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, ru, it, es, de },
})

export function setUiLocale(lang: string | undefined) {
  const l = (lang || 'en').toLowerCase()
  if (l === 'en' || l === 'ru' || l === 'it' || l === 'es' || l === 'de') {
    i18n.global.locale.value = l
  } else {
    i18n.global.locale.value = 'en'
  }
}
