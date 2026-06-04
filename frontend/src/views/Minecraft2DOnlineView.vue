<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { playSfx } from '../audio/sound'
import { startPresencePing, stopPresencePing } from '../telemetry/presence'
import { MINECRAFT_2D_COMING_SOON } from '../config/features'
import { GAME_ASSETS_BASE } from '../config/gameAssets'

const GAME_KEY = 'minecraft_2d_online'
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const wsRef = ref<WebSocket | null>(null)
const snap = ref<Record<string, any> | null>(null)
const toast = ref('')
const chunkCache = ref<Map<string, number[]>>(new Map())
const showExchange = ref(false)

type LootKey = 'sand_block' | 'dirt_block' | 'stone_block' | 'iron_block' | 'raw_diamond' | 'apple'
const LOOT_ITEMS: {
  key: LootKey
  label: string
  accent: string
  stackMax?: number
  smeltable?: boolean
}[] = [
  { key: 'sand_block', label: t('mc2d.loot.sand_block'), accent: '#c4a35a', stackMax: 64 },
  { key: 'dirt_block', label: t('mc2d.loot.dirt_block'), accent: '#8d6e63', stackMax: 64 },
  { key: 'stone_block', label: t('mc2d.loot.stone_block'), accent: '#78909c', smeltable: true },
  { key: 'iron_block', label: t('mc2d.loot.iron_block'), accent: '#90a4ae', smeltable: true },
  { key: 'raw_diamond', label: t('mc2d.loot.raw_diamond'), accent: '#4dd0e1' },
  { key: 'apple', label: t('mc2d.loot.apple'), accent: '#ef5350', stackMax: 64 },
]
type PlaceItem = 'sand_block' | 'dirt_block' | 'stone_block'
const PLACE_SLOTS: { key: PlaceItem; label: string; tile: number }[] = [
  { key: 'sand_block', label: t('mc2d.loot.sand_block'), tile: 1 },
  { key: 'dirt_block', label: t('mc2d.loot.dirt_block'), tile: 2 },
  { key: 'stone_block', label: t('mc2d.loot.stone_block'), tile: 3 },
]
const selectedPlaceItem = ref<PlaceItem>('dirt_block')
const cursorTile = ref<{ tx: number; ty: number } | null>(null)
const reducedMotion = ref(
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
)

const ATLAS_CELL = 32
/** Canvas tile size (matches atlas cell after build). */
const TILE = ATLAS_CELL

const atlasImg = new Image()
const playerImg = new Image()
const TREE_SPRITE_COUNT = 4
const treeImgs: HTMLImageElement[] = Array.from({ length: TREE_SPRITE_COUNT }, () => new Image())
let atlasLoaded = false
let playerLoaded = false
atlasImg.onload = () => {
  atlasLoaded = true
}
atlasImg.onerror = () => {
  atlasLoaded = false
}
playerImg.onload = () => {
  playerLoaded = true
}
atlasImg.src = `${GAME_ASSETS_BASE}/mc2d/atlas.webp`
playerImg.src = `${GAME_ASSETS_BASE}/mc2d/player.webp`
for (let i = 0; i < TREE_SPRITE_COUNT; i++) {
  treeImgs[i].src = `${GAME_ASSETS_BASE}/mc2d/trees/tree${i + 1}.png`
}
const skyImg = new Image()
skyImg.src = `${GAME_ASSETS_BASE}/mc2d/sky.png`
const houseImgs: HTMLImageElement[] = [
  Object.assign(new Image(), { src: `${GAME_ASSETS_BASE}/mc2d/houses/home1.png` }),
  Object.assign(new Image(), { src: `${GAME_ASSETS_BASE}/mc2d/houses/home2.png` }),
]

/** Fallback if atlas failed to load. */
const TILE_COLORS: Record<number, string> = {
  0: 'rgba(120, 180, 255, 0.35)',
  1: '#e6d6a8',
  2: '#8b6914',
  3: '#7a7a82',
  4: '#b87333',
  5: '#6ee7ff',
  6: '#4caf50',
  7: '#2e5c2e',
}

let camX = 0
let camY = 0
let lastChunkCx = 99999
let lastChunkCy = 99999
let keys: Record<string, boolean> = {}
let raf = 0

/** Smooth local player position (server + jump prediction). */
let displayX = 0
let displayY = 0
let displayVy = 0
let displayReady = false
let lastFrameMs = 0
let physTickMs = 50
let gravPerTick = 0.028
let jumpImpulse = -1.3
let jumpOriginY: number | null = null
const JUMP_HEIGHT_TILES = 1.5

type OtherTrack = {
  x0: number
  y0: number
  vy0: number
  t0: number
  x1: number
  y1: number
  vy1: number
  t1: number
}
const otherTracks = new Map<string, OtherTrack>()

const selfInfo = computed(() => (snap.value?.self ?? null) as Record<string, any> | null)
const inWorld = computed(() => Boolean(selfInfo.value?.in_world))
const queuePos = computed(() => (selfInfo.value?.queue_pos == null ? null : Number(selfInfo.value.queue_pos)))
const diamonds = computed(() => Number((auth.otherData as any)?.diamonds ?? 0))

const lootCards = computed(() =>
  LOOT_ITEMS.map((item) => ({
    ...item,
    count: Number(selfInfo.value?.inv?.[item.key] ?? 0),
  }))
)

const totalLootCount = computed(() => lootCards.value.reduce((s, it) => s + it.count, 0))

const smeltableStone = computed(() => Number(selfInfo.value?.inv?.stone_block ?? 0))
const smeltableIron = computed(() => Number(selfInfo.value?.inv?.iron_block ?? 0))
const smeltableTotal = computed(() => smeltableStone.value + smeltableIron.value)

const appleStaminaGain = computed(() => {
  const fromServer = Number(selfInfo.value?.apple_stamina_gain ?? 0)
  if (fromServer > 0) return fromServer
  const max = Number(selfInfo.value?.stamina_max ?? 100)
  return Math.max(1, Math.ceil(max * 0.3))
})

const appleBuyDustCost = computed(() => Number(selfInfo.value?.apple_buy_dust_cost ?? 50))

const canBuyApple = computed(() => {
  const dust = Number(selfInfo.value?.dust ?? 0)
  const apples = Number(selfInfo.value?.inv?.apple ?? 0)
  return dust >= appleBuyDustCost.value && apples < 64
})

const uiTick = ref(0)
let uiTickTimer: number | null = null

const escapeCountdownSec = computed(() => {
  void uiTick.value
  const t = selfInfo.value?.escape?.free_ends_at as number | undefined
  if (t == null) return null
  return Math.max(0, Math.ceil(t - Date.now() / 1000))
})

const escapePanel = computed(() => {
  const s = selfInfo.value
  if (!s?.escape || !inWorld.value) return { show: false as const }
  const e = s.escape as { available?: boolean; free_ends_at?: number }
  const cd = escapeCountdownSec.value
  const pending = e.free_ends_at != null && cd != null && cd > 0
  const show = Boolean(e.available) || pending
  return {
    show,
    pending,
    gh: Number(s.diamonds_gamehub ?? 0),
    available: Boolean(e.available),
  }
})

function syncPhysicsFromSnap() {
  const ph = snap.value?.physics as Record<string, number> | undefined
  if (!ph) return
  physTickMs = Number(ph.tick_ms ?? 50)
  gravPerTick = Number(ph.vy_per_tick ?? 0.028)
  jumpImpulse = Number(ph.jump_impulse ?? -0.46)
}

function reconcileSelf(s: Record<string, unknown>) {
  const sx = Number(s.x ?? 0)
  const sy = Number(s.y ?? 0)
  const sv = Number(s.vy ?? 0)
  if (!displayReady) {
    displayX = sx
    displayY = sy
    displayVy = sv
    displayReady = true
    return
  }
  displayX += (sx - displayX) * 0.45
  const err = sy - displayY
  const inAir = sy < -0.04 || displayY < -0.04
  if (Math.abs(err) > 1.2) {
    displayY = sy
    displayVy = sv
  } else if (inAir) {
    displayY += err * 0.45
    displayVy = Math.max(displayVy * 0.35 + sv * 0.65, gravPerTick)
  } else {
    displayY += err * 0.35
    displayVy = displayVy * 0.55 + sv * 0.45
  }
  if (sv >= -0.02 && sy >= -0.05) {
    jumpOriginY = null
  }
}

function trackOtherPlayers(players: Record<string, unknown>[]) {
  const now = performance.now()
  for (const p of players) {
    const un = String(p.username ?? '')
    if (!un) continue
    const prev = otherTracks.get(un)
    const x1 = Number(p.x ?? 0)
    const y1 = Number(p.y ?? 0)
    const vy1 = Number(p.vy ?? 0)
    otherTracks.set(un, {
      x0: prev?.x1 ?? x1,
      y0: prev?.y1 ?? y1,
      vy0: prev?.vy1 ?? vy1,
      t0: prev?.t1 ?? now - physTickMs,
      x1,
      y1,
      vy1,
      t1: now,
    })
  }
}

function otherDrawPos(p: Record<string, unknown>): { x: number; y: number } {
  const un = String(p.username ?? '')
  const st = otherTracks.get(un)
  if (!st) return { x: Number(p.x ?? 0), y: Number(p.y ?? 0) }
  const now = performance.now()
  const span = Math.max(16, st.t1 - st.t0)
  let u = (now - st.t0) / span
  if (u > 1.1) {
    const extra = (now - st.t1) / 1000
    const gSec = gravPerTick / (physTickMs / 1000)
    return { x: st.x1, y: st.y1 + st.vy1 * extra + 0.5 * gSec * extra * extra }
  }
  u = Math.min(1, u)
  return {
    x: st.x0 + (st.x1 - st.x0) * u,
    y: st.y0 + (st.y1 - st.y0) * u,
  }
}

function stepDisplayPhysics() {
  if (!displayReady || !inWorld.value) return
  const now = performance.now()
  if (!lastFrameMs) {
    lastFrameMs = now
    return
  }
  let dt = now - lastFrameMs
  lastFrameMs = now
  const tick = physTickMs
  while (dt >= tick) {
    displayVy += gravPerTick
    displayY += displayVy * (tick / 1000)
    dt -= tick
    if (jumpOriginY != null && displayY < jumpOriginY - JUMP_HEIGHT_TILES) {
      displayY = jumpOriginY - JUMP_HEIGHT_TILES
      if (displayVy < 0) displayVy = 0
    }
  }
  if (dt > 0) {
    displayY += displayVy * (dt / 1000)
  }
  if (jumpOriginY != null && displayY < jumpOriginY - JUMP_HEIGHT_TILES) {
    displayY = jumpOriginY - JUMP_HEIGHT_TILES
    if (displayVy < 0) displayVy = 0
  }
}

function connectWs() {
  if (!auth.token) return
  wsRef.value?.close()
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/ws/minecraft-2d-online?token=${encodeURIComponent(auth.token)}`
  const ws = new WebSocket(url)
  wsRef.value = ws
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'snapshot') {
        snap.value = msg
        syncPhysicsFromSnap()
        const self = msg.self as Record<string, unknown> | undefined
        if (self?.in_world) reconcileSelf(self)
        trackOtherPlayers((msg.players as Record<string, unknown>[]) ?? [])
        void ensureChunksForView()
      } else if (msg.type === 'patches') {
        applyPatches(msg)
        if (msg.week_reset) toast.value = t('mc2d.toasts.weekReset')
      } else if (msg.type === 'action_result') {
        if (msg.ok === false) toast.value = String(msg.error ?? t('errors.generic'))
        const pl = msg.payload
        if (pl && pl.ok === true && pl.tx != null && pl.ty != null) {
          const tx = Number(pl.tx)
          const ty = Number(pl.ty)
          const newT = pl.set_tile != null ? Number(pl.set_tile) : 0
          if (!setTile(tx, ty, newT)) {
            const s2 = selfInfo.value
            const cs = Number(snap.value?.chunk_size ?? 32)
            if (s2 && snap.value && auth.token) {
              void loadChunks(Math.floor(tx / cs), Math.floor(ty / cs)).then(() => setTile(tx, ty, newT))
            }
          }
        }
        if (pl?.tree_removed_x != null && snap.value?.trees) {
          const rx = Number(pl.tree_removed_x)
          snap.value = {
            ...snap.value,
            trees: (snap.value.trees as { x: number }[]).filter((t) => Number(t.x) !== rx),
          }
        }
        if (pl?.ok && pl.stamina_gain != null) {
          toast.value = t('mc2d.toasts.staminaGain', { amount: Number(pl.stamina_gain) })
        } else if (pl?.ok && pl.apples != null && pl.dust_spent != null) {
          toast.value = t('mc2d.toasts.appleBought', { dust: Number(pl.dust_spent) })
        } else if (pl?.ok && pl.dust_gain != null) {
          const st = Number(pl.smelted_stone ?? 0)
          const ir = Number(pl.smelted_iron ?? 0)
          toast.value = t('mc2d.toasts.smelted', { dust: Number(pl.dust_gain), stone: st, iron: ir })
          void auth.refreshProfile()
        } else if (pl?.ok && pl.gained) {
          toast.value = t('mc2d.toasts.dustGain', { dust: Number(pl.gained) })
          void auth.refreshProfile()
        } else if (pl?.ok && pl.diamonds != null) {
          void auth.refreshProfile()
        } else if (pl?.escape || pl?.teleport === 'base') {
          toast.value = t('mc2d.toasts.teleportBase')
          void auth.refreshProfile()
        }
      }
    } catch {
      /* ignore */
    }
  }
}

function send(obj: Record<string, unknown>) {
  const ws = wsRef.value
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj))
}

function applyPatches(msg: any) {
  for (const c of msg.refill ?? []) {
    setTile(Number(c.x), Number(c.y), Number(c.t))
  }
  for (const d of msg.diamonds ?? []) {
    setTile(Number(d.x), Number(d.y), 5)
  }
}

function setTile(gx: number, gy: number, t: number): boolean {
  const cs = Number(snap.value?.chunk_size ?? 32)
  const cx = Math.floor(gx / cs)
  const cy = Math.floor(gy / cs)
  const key = `${cx},${cy}`
  const prev = chunkCache.value.get(key)
  if (!prev) return false
  const lx = gx - cx * cs
  const ly = gy - cy * cs
  const idx = ly * cs + lx
  if (idx < 0 || idx >= prev.length) return false
  const next = [...prev]
  next[idx] = t
  const m = new Map(chunkCache.value)
  m.set(key, next)
  chunkCache.value = m
  return true
}

async function loadChunks(cx: number, cy: number) {
  if (!auth.token) return
  const r = 2
  const resp = await fetch(`/api/minecraft-2d-online/chunks?cx=${cx}&cy=${cy}&r=${r}`, {
    headers: { Authorization: `Bearer ${auth.token}` },
  })
  if (!resp.ok) return
  const data = await resp.json()
  const chunks = data.chunks ?? {}
  const m = new Map(chunkCache.value)
  for (const [k, arr] of Object.entries(chunks)) {
    if (Array.isArray(arr)) m.set(k, arr.map((x) => Number(x)))
  }
  chunkCache.value = m
}

async function ensureChunksForView() {
  const s = selfInfo.value
  if (!s || !snap.value) return
  const cs = Number(snap.value.chunk_size ?? 32)
  const gx = Math.floor(Number(s.x ?? 0))
  const gy = Math.floor(Number(s.y ?? 0))
  const cx = Math.floor(gx / cs)
  const cy = Math.floor(gy / cs)
  if (cx !== lastChunkCx || cy !== lastChunkCy) {
    lastChunkCx = cx
    lastChunkCy = cy
    await loadChunks(cx, cy)
  }
}

/** Old TILE.TREE (7) → sand under tree sprite. */
function normalizeTileId(t: number): number {
  return t === 7 ? 1 : t
}

function getTile(gx: number, gy: number): number {
  const cs = Number(snap.value?.chunk_size ?? 32)
  const cx = Math.floor(gx / cs)
  const cy = Math.floor(gy / cs)
  const arr = chunkCache.value.get(`${cx},${cy}`)
  if (!arr) return 0
  const lx = gx - cx * cs
  const ly = gy - cy * cs
  if (lx < 0 || ly < 0 || lx >= cs || ly >= cs) return 0
  return normalizeTileId(Number(arr[ly * cs + lx] ?? 0))
}

function atBase(): boolean {
  const s = selfInfo.value
  if (!s || !snap.value) return false
  const sky = Number(snap.value.sky_rows ?? 1)
  const py = Math.floor(Number(s.y ?? 0))
  const px = Math.floor(Number(s.x ?? 0))
  if (py > sky + 6) return false
  const r = Number(snap.value.base_zone_radius ?? 8)
  const houses = (snap.value.houses as { x: number }[] | undefined) ?? []
  if (houses.length) return houses.some((h) => Math.abs(px - Number(h.x)) <= r)
  const bx = Number(snap.value.base_x ?? 0)
  return Math.abs(px - bx) <= r
}

function drawSky(ctx: CanvasRenderingContext2D, w: number, h: number, surfaceY: number) {
  if (!skyImg.naturalWidth) return
  const surfaceScreenY = surfaceY * TILE - camY
  if (surfaceScreenY < -h) return
  const parallaxX = camX * 0.32
  const parallaxY = camY * 0.1
  const zoom = Math.max(w / skyImg.naturalWidth, 0.85)
  const dw = skyImg.naturalWidth * zoom
  const dh = skyImg.naturalHeight * zoom
  const top = surfaceScreenY - dh + TILE * 0.6
  let x = -(((parallaxX % dw) + dw) % dw) - dw
  while (x < w + dw) {
    ctx.drawImage(skyImg, x, top - parallaxY, dw, dh)
    x += dw
  }
}

function drawHouses(ctx: CanvasRenderingContext2D, surfaceY: number, x0: number, x1: number) {
  for (const h of snap.value?.houses ?? []) {
    const gx = Number(h.x)
    if (gx < x0 - 8 || gx > x1 + 8) continue
    const gy = Number(h.y ?? surfaceY)
    const v = Math.min(1, Math.max(0, Number(h.v ?? 0)))
    const img = houseImgs[v]
    if (!img?.naturalWidth) continue
    const sx = Math.floor(gx * TILE - camX)
    const groundY = Math.floor(gy * TILE - camY)
    const hh = Math.round(TILE * 6.25)
    const hw = Math.round(img.naturalWidth * (hh / img.naturalHeight))
    ctx.drawImage(img, sx + (TILE - hw) / 2, groundY - hh, hw, hh)
  }
}

function draw() {
  const c = canvasRef.value
  const s = selfInfo.value
  if (!c || !s) return
  const ctx = c.getContext('2d')
  if (!ctx) return
  stepDisplayPhysics()
  const w = c.width
  const h = c.height
  ctx.fillStyle = '#0a1020'
  ctx.fillRect(0, 0, w, h)
  const surfaceY = Number(snap.value?.sky_rows ?? 1)
  const myX = displayReady ? displayX : Number(s.x ?? 0)
  const myY = displayReady ? displayY : Number(s.y ?? 0)
  camX = myX * TILE - w / 2 + TILE / 2
  camY = myY * TILE - h / 2 + TILE / 2
  const gw = Number(snap.value?.width ?? 240)
  const gh = Number(snap.value?.sky_rows ?? 1) + Number(snap.value?.depth ?? 128)
  const x0 = Math.max(0, Math.floor(camX / TILE) - 1)
  const y0 = Math.max(0, Math.floor(camY / TILE) - 1)
  const x1 = Math.min(gw - 1, Math.ceil((camX + w) / TILE) + 1)
  const y1 = Math.min(gh - 1, Math.ceil((camY + h) / TILE) + 1)
  drawSky(ctx, w, h, surfaceY)
  const useAtlas = atlasLoaded && atlasImg.naturalWidth >= ATLAS_CELL * 8
  for (let gy = y0; gy <= y1; gy++) {
    for (let gx = x0; gx <= x1; gx++) {
      const t = getTile(gx, gy)
      const sx = Math.floor(gx * TILE - camX)
      const sy = Math.floor(gy * TILE - camY)
      if (t === 0) {
        if (gy > surfaceY) {
          ctx.fillStyle = TILE_COLORS[0] ?? 'rgba(120,180,255,0.35)'
          ctx.fillRect(sx, sy, TILE, TILE)
        }
      } else if (useAtlas && t >= 1 && t <= 6) {
        ctx.drawImage(atlasImg, t * ATLAS_CELL, 0, ATLAS_CELL, ATLAS_CELL, sx, sy, TILE, TILE)
      } else {
        ctx.fillStyle = TILE_COLORS[t] ?? '#444'
        ctx.fillRect(sx, sy, TILE - 1, TILE - 1)
      }
    }
  }
  drawHouses(ctx, surfaceY, x0, x1)
  if (treeImgs.some((img) => img.naturalWidth > 0)) {
    for (const tr of snap.value?.trees ?? []) {
      const gx = Number(tr.x)
      const gy = Number(tr.y ?? surfaceY)
      if (gx < x0 - 1 || gx > x1 + 1 || gy < y0 - 2 || gy > y1 + 2) continue
      const v = Math.min(3, Math.max(0, Number(tr.v ?? 0)))
      const img = treeImgs[v]
      if (!img?.naturalWidth) continue
      const sx = Math.floor(gx * TILE - camX)
      const groundY = Math.floor(gy * TILE - camY)
      const th = Math.round(TILE * 4.8)
      const tw = Math.round(img.naturalWidth * (th / img.naturalHeight))
      ctx.drawImage(img, sx + (TILE - tw) / 2, groundY - th, tw, th)
    }
  }
  for (const a of snap.value?.apples ?? []) {
    const sx = Math.floor(Number(a.x) * TILE - camX)
    const sy = Math.floor(Number(a.y) * TILE - camY)
    ctx.fillStyle = '#e53935'
    ctx.beginPath()
    ctx.arc(sx + TILE / 2, sy + TILE / 2, TILE / 4, 0, Math.PI * 2)
    ctx.fill()
  }
  for (const p of snap.value?.players ?? []) {
    const isSelf = p.username === auth.username
    const pos = isSelf ? { x: myX, y: myY } : otherDrawPos(p as Record<string, unknown>)
    const sx = Math.floor(pos.x * TILE - camX)
    const sy = Math.floor(pos.y * TILE - camY)
    const faceLeft = Boolean(p.face_left)
    if (playerLoaded && playerImg.naturalWidth > 0) {
      const ph = Math.round(TILE * 1.35)
      const pw = Math.round(playerImg.naturalWidth * (ph / playerImg.naturalHeight))
      const px = sx + (TILE - pw) / 2
      const py = sy + TILE - ph
      const ax = sx + TILE / 2
      const ay = py + ph / 2
      ctx.save()
      ctx.translate(ax, ay)
      if (faceLeft) ctx.scale(-1, 1)
      ctx.drawImage(playerImg, -pw / 2, -ph / 2, pw, ph)
      ctx.restore()
    } else {
      ctx.save()
      ctx.translate(sx + TILE / 2, sy + TILE / 2)
      if (faceLeft) ctx.scale(-1, 1)
      ctx.fillStyle = p.username === auth.username ? '#ffeb3b' : '#90caf9'
      ctx.fillRect(-(TILE - 8) / 2, -(TILE - 4) / 2, TILE - 8, TILE - 4)
      ctx.restore()
    }
  }
}

function loop() {
  draw()
  raf = requestAnimationFrame(loop)
}

function tileAtScreen(mx: number, my: number): { tx: number; ty: number } {
  return {
    tx: Math.floor((mx + camX) / TILE),
    ty: Math.floor((my + camY) / TILE),
  }
}

function selectPlaceSlot(idx: number) {
  const slot = PLACE_SLOTS[idx]
  if (slot) selectedPlaceItem.value = slot.key
}

function placeBlockAtCursor() {
  const s = selfInfo.value
  const cur = cursorTile.value
  if (!s || !inWorld.value || !cur) return
  if (Number(s.inv?.[selectedPlaceItem.value] ?? 0) < 1) {
    toast.value = t('mc2d.errors.noBlocks')
    return
  }
  playSfx('button')
  send({ type: 'place', tx: cur.tx, ty: cur.ty, item: selectedPlaceItem.value })
}

function onKeyDown(e: KeyboardEvent) {
  const target = e.target as HTMLElement | null
  if (target?.closest?.('input, textarea, select, [contenteditable=true]')) return
  keys[e.code] = true
  if (inWorld.value && e.code === 'Space' && !e.repeat) {
    e.preventDefault()
    send({ type: 'jump' })
    if (displayVy > -0.12) {
      displayVy = jumpImpulse
      jumpOriginY = displayY
    }
  }
  if (inWorld.value && !e.repeat) {
    if (e.code === 'KeyR') {
      e.preventDefault()
      placeBlockAtCursor()
    } else if (e.code === 'Digit1') {
      selectPlaceSlot(0)
    } else if (e.code === 'Digit2') {
      selectPlaceSlot(1)
    } else if (e.code === 'Digit3') {
      selectPlaceSlot(2)
    }
  }
  if (!inWorld.value) return
  const block = ['ArrowLeft', 'ArrowRight', 'Space', 'KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyR']
  if (block.includes(e.code)) e.preventDefault()
}

function onKeyUp(e: KeyboardEvent) {
  keys[e.code] = false
}

function tickInput() {
  if (!inWorld.value) return
  let dx = 0
  if (keys['ArrowLeft'] || keys['KeyA']) dx = -1
  if (keys['ArrowRight'] || keys['KeyD']) dx = 1
  send({ type: 'move', dx, dy: 0 })
}

let inputTimer: number | null = null

function onCanvasMove(ev: MouseEvent) {
  const c = canvasRef.value
  if (!c || !inWorld.value) return
  const r = c.getBoundingClientRect()
  cursorTile.value = tileAtScreen(ev.clientX - r.left, ev.clientY - r.top)
}

function onCanvasClick(ev: MouseEvent) {
  const c = canvasRef.value
  const s = selfInfo.value
  if (!c || !s || !inWorld.value) return
  const r = c.getBoundingClientRect()
  const { tx: gx, ty: gy } = tileAtScreen(ev.clientX - r.left, ev.clientY - r.top)
  playSfx('button')
  send({ type: 'mine', tx: gx, ty: gy })
}

function joinWorld() {
  playSfx('button')
  send({ type: 'join_world' })
}

function leaveWorld() {
  playSfx('button')
  displayReady = false
  jumpOriginY = null
  otherTracks.clear()
  send({ type: 'leave_world' })
}

function openExchange() {
  playSfx('button')
  showExchange.value = true
}

function doExchange() {
  const idem = crypto.randomUUID()
  send({ type: 'exchange_diamond_for_dust', idempotency_key: idem })
  showExchange.value = false
}

function smeltAll() {
  if (smeltableTotal.value <= 0) return
  playSfx('button')
  send({ type: 'smelt' })
}

function eatApple() {
  playSfx('button')
  send({ type: 'use_apple' })
}

function buyApple() {
  playSfx('button')
  send({ type: 'buy_apple' })
}

function deliverDiamond() {
  playSfx('button')
  send({ type: 'deliver_raw_diamond', idempotency_key: crypto.randomUUID() })
}

function escapeSurfacePaid() {
  playSfx('button')
  send({ type: 'escape_surface_paid' })
}

function teleportBasePaid() {
  playSfx('button')
  send({ type: 'teleport_base_paid' })
}

function escapeSurfaceFree() {
  playSfx('button')
  send({ type: 'escape_surface_free' })
}

watch(
  () => selfInfo.value?.x,
  () => {
    void ensureChunksForView()
  }
)

onMounted(() => {
  if (MINECRAFT_2D_COMING_SOON) return
  void auth.refreshProfile()
  startPresencePing(auth.token || '', GAME_KEY)
  const c = canvasRef.value
  if (c) {
    c.width = Math.min(920, window.innerWidth - 32)
    c.height = Math.min(520, window.innerHeight - 220)
  }
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  uiTickTimer = window.setInterval(() => {
    uiTick.value++
  }, 400)
  connectWs()
  inputTimer = window.setInterval(tickInput, 50)
  raf = requestAnimationFrame(loop)
})

onBeforeUnmount(() => {
  stopPresencePing()
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  if (uiTickTimer) window.clearInterval(uiTickTimer)
  uiTickTimer = null
  if (inputTimer) window.clearInterval(inputTimer)
  cancelAnimationFrame(raf)
  wsRef.value?.close()
})
</script>

<template>
  <div v-if="MINECRAFT_2D_COMING_SOON" class="mc2d-wip">
    <header class="mc2d-top">
      <button type="button" class="btn mc2d-back" @click="router.push('/games')">← {{ t('mc2d.nav.hub') }}</button>
      <h1 class="mc2d-title">Minecraft 2D Online</h1>
    </header>
    <div class="mc2d-wip-card">
      <h2 class="mc2d-wip-title">{{ t('hub.status.inDevelopment') }}</h2>
      <p class="mc2d-wip-text">{{ t('mc2d.wip.unavailable') }}</p>
      <button type="button" class="btn btn-primary mc2d-bigbtn" @click="router.push('/games')">{{ t('mc2d.wip.backToHub') }}</button>
    </div>
  </div>
  <div v-else class="mc2d-root" :class="{ 'mc2d-root--motion': !reducedMotion }">
    <header class="mc2d-top">
      <button type="button" class="btn mc2d-back" @click="router.push('/games')">← {{ t('mc2d.nav.hub') }}</button>
      <h1 class="mc2d-title">Minecraft 2D Online</h1>
      <div class="mc2d-meta">
        <span>{{ t('mc2d.hud.diamonds', { diamonds }) }}</span>
      </div>
    </header>

    <div v-if="toast" class="mc2d-toast" role="status">{{ toast }}</div>

    <div class="mc2d-layout">
      <canvas
        ref="canvasRef"
        class="mc2d-canvas"
        @click="onCanvasClick"
        @mousemove="onCanvasMove"
        @mouseleave="cursorTile = null"
      />

      <aside class="mc2d-panel">
        <div v-if="!inWorld" class="mc2d-lobby">
          <p v-if="queuePos">{{ t('mc2d.lobby.queuePos', { pos: queuePos }) }}</p>
          <p v-else>{{ t('mc2d.lobby.hint') }}</p>
          <button type="button" class="btn btn-primary mc2d-bigbtn" @click="joinWorld">{{ t('mc2d.lobby.joinWorld') }}</button>
        </div>
        <div v-else>
          <button type="button" class="btn mc2d-bigbtn" @click="leaveWorld">{{ t('mc2d.lobby.leaveToLobby') }}</button>
          <p class="mc2d-depth">{{ t('mc2d.hud.depth', { depth: Math.max(0, Math.floor(Number(selfInfo?.y ?? 0))) }) }}</p>
        </div>

        <div class="mc2d-hud">
          <div class="mc2d-energy">
            <span>{{ t('mc2d.hud.stamina') }}</span>
            <div class="mc2d-bar">
              <div
                class="mc2d-bar-fill"
                :style="{ width: `${Math.round((100 * Number(selfInfo?.stamina ?? 0)) / Math.max(1, Number(selfInfo?.stamina_max ?? 100)))}%` }"
              />
            </div>
          </div>
          <p>{{ t('mc2d.hud.pickaxe', { level: Number(selfInfo?.pickaxe ?? 0) }) }}</p>
          <div class="mc2d-dust-card">
            <div class="mc2d-dust-head">
              <span class="mc2d-dust-title">{{ t('mc2d.hud.dustTitle') }}</span>
              <span class="mc2d-dust-value">{{ selfInfo?.dust ?? 0 }}</span>
            </div>
            <p class="mc2d-dust-meta">{{ t('mc2d.hud.exchangeRate', { rate: selfInfo?.dust_rate ?? '?' }) }}</p>
          </div>
          <div class="mc2d-loot">
            <div class="mc2d-loot-head">
              <span>{{ t('mc2d.hud.loot') }}</span>
              <span class="mc2d-loot-total">{{ totalLootCount }}</span>
            </div>
            <div class="mc2d-loot-grid">
              <div
                v-for="item in lootCards"
                :key="item.key"
                class="mc2d-loot-card"
                :class="{ 'mc2d-loot-card--has': item.count > 0, 'mc2d-loot-card--ore': item.smeltable }"
                :style="{ '--loot-accent': item.accent }"
              >
                <span class="mc2d-loot-count">{{ item.count }}</span>
                <span class="mc2d-loot-label">{{ item.label }}</span>
                <div v-if="item.stackMax" class="mc2d-loot-bar">
                  <div
                    class="mc2d-loot-bar-fill"
                    :style="{ width: `${Math.min(100, (100 * item.count) / item.stackMax)}%` }"
                  />
                </div>
              </div>
            </div>
          </div>
          <div v-if="inWorld" class="mc2d-hotbar">
            <button
              v-for="(slot, i) in PLACE_SLOTS"
              :key="slot.key"
              type="button"
              class="mc2d-hotbar-slot"
              :class="{ 'mc2d-hotbar-slot--active': selectedPlaceItem === slot.key }"
              @click="selectPlaceSlot(i)"
            >
              <span class="mc2d-hotbar-label">{{ slot.label }}</span>
              <span class="mc2d-hotbar-count">{{ selfInfo?.inv?.[slot.key] ?? 0 }}</span>
              <span class="mc2d-hotbar-key">{{ i + 1 }}</span>
            </button>
          </div>
        </div>

        <div class="mc2d-actions">
          <button
            v-if="inWorld && diamonds >= 1"
            type="button"
            class="btn btn-primary"
            @click="teleportBasePaid"
          >
            {{ t('mc2d.actions.basePaid') }}
          </button>
          <button v-if="inWorld && atBase()" type="button" class="btn" @click="openExchange">
            {{ t('mc2d.actions.exchange') }}
          </button>
          <button
            v-if="inWorld && atBase() && smeltableTotal > 0"
            type="button"
            class="btn btn-primary mc2d-smelt-all"
            @click="smeltAll"
          >
            {{ t('mc2d.actions.smeltAll') }}
            <span class="mc2d-smelt-detail">{{ t('mc2d.actions.smeltDetail', { stone: smeltableStone, iron: smeltableIron }) }}</span>
          </button>
          <button v-if="Number(selfInfo?.inv?.apple ?? 0) > 0" type="button" class="btn" @click="eatApple">
            {{ t('mc2d.actions.eatApple', { energy: appleStaminaGain }) }}
          </button>
          <button
            v-if="inWorld && atBase()"
            type="button"
            class="btn"
            :disabled="!canBuyApple"
            @click="buyApple"
          >
            {{ t('mc2d.actions.buyApple', { dust: appleBuyDustCost }) }}
          </button>
          <button v-if="inWorld && atBase() && Number(selfInfo?.inv?.raw_diamond ?? 0) > 0" type="button" class="btn btn-primary" @click="deliverDiamond">
            {{ t('mc2d.actions.deliverDiamond') }}
          </button>
        </div>

        <div v-if="escapePanel.show" class="mc2d-escape">
          <p v-if="escapePanel.pending" class="mc2d-escape-wait">
            {{ t('mc2d.escape.pending', { seconds: escapeCountdownSec }) }}
          </p>
          <template v-else-if="escapePanel.available">
            <p class="mc2d-escape-title">{{ t('mc2d.escape.title') }}</p>
            <p v-if="escapePanel.gh >= 1" class="mc2d-escape-hint">{{ t('mc2d.escape.ghDiamonds', { diamonds: escapePanel.gh }) }}</p>
            <p v-else class="mc2d-escape-hint">{{ t('mc2d.escape.noDiamonds') }}</p>
            <div class="mc2d-escape-btns">
              <button
                v-if="escapePanel.gh >= 1"
                type="button"
                class="btn btn-primary mc2d-bigbtn"
                @click="escapeSurfacePaid"
              >
                {{ t('mc2d.escape.paid') }}
              </button>
              <button type="button" class="btn mc2d-bigbtn" @click="escapeSurfaceFree">{{ t('mc2d.escape.free') }}</button>
            </div>
          </template>
        </div>

        <p class="mc2d-hint">
          {{ t('mc2d.hint.controls') }}
          {{ ' ' }}
          {{ t('mc2d.hint.persist') }}
        </p>
        <a class="mc2d-credits" href="/CREDITS_mc2d.md" target="_blank" rel="noopener">CREDITS</a>
      </aside>
    </div>

    <Teleport to="body">
      <div v-if="showExchange" class="mc2d-modal-overlay" @click.self="showExchange = false">
        <div class="mc2d-modal">
          <h3>{{ t('mc2d.exchange.title') }}</h3>
          <p>{{ t('mc2d.exchange.rate', { rate: selfInfo?.dust_rate ?? '?' }) }}</p>
          <p>{{ t('mc2d.exchange.balance', { diamonds }) }}</p>
          <div class="mc2d-modal-actions">
            <button type="button" class="btn" @click="showExchange = false">{{ t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary" :disabled="diamonds < 1" @click="doExchange">{{ t('mc2d.exchange.spend') }}</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<style scoped>
.mc2d-wip {
  min-height: 100vh;
  padding: 12px 16px 24px;
  background: linear-gradient(180deg, #0d1528 0%, #050810 100%);
  color: #e8eef8;
}
.mc2d-wip-card {
  max-width: 420px;
  margin: 48px auto 0;
  padding: 24px;
  border-radius: 16px;
  background: rgba(12, 18, 36, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.12);
  text-align: center;
}
.mc2d-wip-title {
  margin: 0 0 12px;
  font-size: 1.35rem;
}
.mc2d-wip-text {
  margin: 0 0 20px;
  opacity: 0.9;
}
.mc2d-root {
  min-height: 100vh;
  padding: 12px 16px 24px;
  background: linear-gradient(180deg, #0d1528 0%, #050810 100%);
  color: #e8eef8;
}
.mc2d-root--motion .mc2d-toast {
  animation: mc2dFade 0.25s ease-out;
}
@keyframes mc2dFade {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.mc2d-top {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.mc2d-title {
  margin: 0;
  font-size: 1.25rem;
  flex: 1;
}
.mc2d-layout {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: flex-start;
}
.mc2d-canvas {
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  cursor: crosshair;
  max-width: 100%;
  background: #050810;
}
.mc2d-panel {
  flex: 1;
  min-width: 240px;
  max-width: 360px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(12, 18, 36, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.mc2d-bigbtn {
  min-height: 44px;
  width: 100%;
  margin-top: 8px;
}
.mc2d-hud {
  margin-top: 12px;
  font-size: 0.95rem;
}
.mc2d-dust-card {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(77, 208, 225, 0.22), rgba(126, 87, 194, 0.18));
  border: 1px solid rgba(144, 202, 249, 0.35);
}
.mc2d-dust-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.mc2d-dust-title {
  font-size: 0.85rem;
  opacity: 0.92;
}
.mc2d-dust-value {
  font-size: 1.5rem;
  font-weight: 800;
  color: #b3e5fc;
  text-shadow: 0 0 12px rgba(77, 208, 225, 0.45);
}
.mc2d-dust-meta {
  margin: 6px 0 0;
  font-size: 0.78rem;
  opacity: 0.8;
}
.mc2d-loot {
  margin-top: 12px;
}
.mc2d-loot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 0.88rem;
  font-weight: 600;
}
.mc2d-loot-total {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  font-variant-numeric: tabular-nums;
}
.mc2d-loot-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.mc2d-loot-card {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.22);
  opacity: 0.55;
  transition:
    opacity 0.2s ease,
    transform 0.2s ease,
    border-color 0.2s ease;
}
.mc2d-loot-card--has {
  opacity: 1;
  border-color: color-mix(in srgb, var(--loot-accent) 55%, transparent);
  background: color-mix(in srgb, var(--loot-accent) 14%, rgba(0, 0, 0, 0.35));
}
.mc2d-root--motion .mc2d-loot-card--has {
  animation: mc2dLootPulse 2.4s ease-in-out infinite;
}
.mc2d-loot-card--ore.mc2d-loot-card--has {
  box-shadow: inset 0 0 0 1px rgba(255, 235, 59, 0.25);
}
.mc2d-loot-count {
  display: block;
  font-size: 1.35rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--loot-accent);
  line-height: 1.1;
}
.mc2d-loot-label {
  display: block;
  margin-top: 2px;
  font-size: 0.72rem;
  opacity: 0.88;
}
.mc2d-loot-bar {
  height: 4px;
  margin-top: 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.35);
  overflow: hidden;
}
.mc2d-loot-bar-fill {
  height: 100%;
  border-radius: 4px;
  background: var(--loot-accent);
  transition: width 0.25s ease-out;
}
@keyframes mc2dLootPulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.02);
  }
}
.mc2d-smelt-all {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  line-height: 1.25;
}
.mc2d-smelt-detail {
  font-size: 0.78rem;
  font-weight: 500;
  opacity: 0.88;
}
.mc2d-hotbar {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.mc2d-hotbar-slot {
  flex: 1;
  min-width: 72px;
  padding: 8px 6px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  cursor: pointer;
  text-align: center;
  position: relative;
}
.mc2d-hotbar-slot--active {
  border-color: #90caf9;
  box-shadow: 0 0 0 1px rgba(144, 202, 249, 0.35);
}
.mc2d-hotbar-label {
  display: block;
  font-size: 0.78rem;
  opacity: 0.9;
}
.mc2d-hotbar-count {
  display: block;
  font-weight: 700;
  font-size: 1rem;
}
.mc2d-hotbar-key {
  position: absolute;
  top: 4px;
  right: 6px;
  font-size: 0.7rem;
  opacity: 0.55;
}
.mc2d-bar {
  height: 10px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.35);
  overflow: hidden;
  margin-top: 4px;
}
.mc2d-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #2e7d32, #c6ff00);
  border-radius: 6px;
  transition: width 0.2s ease-out;
}
.mc2d-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.mc2d-hint {
  margin-top: 12px;
  font-size: 0.82rem;
  opacity: 0.85;
  line-height: 1.4;
}
.mc2d-escape {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(80, 40, 20, 0.45);
  border: 1px solid rgba(255, 200, 120, 0.25);
}
.mc2d-escape-title {
  margin: 0 0 8px 0;
  font-weight: 700;
}
.mc2d-escape-hint {
  margin: 0 0 10px 0;
  font-size: 0.9rem;
  opacity: 0.92;
}
.mc2d-escape-wait {
  margin: 0;
  font-weight: 600;
  color: #ffcc80;
}
.mc2d-escape-btns {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mc2d-credits {
  display: inline-block;
  margin-top: 10px;
  color: #90caf9;
}
.mc2d-toast {
  margin: 6px 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(30, 40, 70, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.mc2d-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  padding: 16px;
}
.mc2d-modal {
  background: #121a2e;
  border-radius: 16px;
  padding: 18px 20px;
  max-width: 400px;
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}
.mc2d-modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
