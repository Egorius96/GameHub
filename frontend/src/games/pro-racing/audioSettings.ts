import { ref, watch } from 'vue'

const LS_MUSIC = 'gamehub_pr_music'
const LS_SFX = 'gamehub_pr_sfx'

function loadBool(key: string, defaultValue: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return defaultValue
    return v === '1'
  } catch {
    return defaultValue
  }
}

export const proRacingMusicEnabled = ref(loadBool(LS_MUSIC, true))
export const proRacingSfxEnabled = ref(loadBool(LS_SFX, true))

watch(proRacingMusicEnabled, (on) => {
  try {
    localStorage.setItem(LS_MUSIC, on ? '1' : '0')
  } catch {
    /* ignore */
  }
})

watch(proRacingSfxEnabled, (on) => {
  try {
    localStorage.setItem(LS_SFX, on ? '1' : '0')
  } catch {
    /* ignore */
  }
})
