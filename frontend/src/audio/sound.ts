import { proRacingMusicEnabled, proRacingSfxEnabled } from '../games/pro-racing/audioSettings'

let unlocked = false

const sfx: Record<string, HTMLAudioElement> = {
  button: new Audio('/assets/original_music/button.mp3'),
  diamond: new Audio('/assets/original_music/diamond.mp3'),
  rock: new Audio('/assets/original_music/rockhit.mp3'),
  gameover: new Audio('/assets/original_music/gameover.mp3'),
  purchase: new Audio('/assets/original_music/purchase.mp3'),
}

const gameMusicList = [
  '/assets/original_music/main_theme.mp3',
  '/assets/original_music/main_theme_2.mp3',
  '/assets/original_music/game_sound_1.mp3',
  '/assets/original_music/game_sound_2.mp3',
  '/assets/original_music/game_sound_3.mp3',
  '/assets/original_music/game_sound_5.mp3',
  '/assets/original_music/game_sound_6.mp3',
]
let gameMusic: HTMLAudioElement | null = null

function unlockAudio() {
  if (unlocked) return
  unlocked = true
  for (const a of Object.values(sfx)) {
    a.volume = 0.25
    a.preload = 'auto'
    try {
      a.load()
    } catch {
      /* ignore */
    }
  }
}

/** Звуки вне Pro Racing (логин, тамагочи и т.д.) */
export function playSfx(name: keyof typeof sfx) {
  unlockAudio()
  const a = sfx[name]
  try {
    a.currentTime = 0
    void a.play()
  } catch {
    /* ignore autoplay restrictions */
  }
}

/** SFX только для экранов Pro Racing — учитывает настройку «все звуки» */
export function playProRacingSfx(name: keyof typeof sfx) {
  if (!proRacingSfxEnabled.value) return
  playSfx(name)
}

export function stopGameMusicOnly() {
  if (gameMusic) {
    try {
      gameMusic.pause()
      gameMusic.currentTime = 0
    } catch {
      /* ignore */
    }
    gameMusic = null
  }
}

export function startGameMusic() {
  if (!proRacingMusicEnabled.value) {
    stopGameMusicOnly()
    return
  }
  unlockAudio()
  if (gameMusic) return
  const pick = gameMusicList[Math.floor(Math.random() * gameMusicList.length)]
  gameMusic = new Audio(pick)
  gameMusic.loop = true
  gameMusic.volume = 0.15
  try {
    void gameMusic.play()
  } catch {
    /* ignore autoplay restrictions */
  }
}

export function stopMusic() {
  stopGameMusicOnly()
}
