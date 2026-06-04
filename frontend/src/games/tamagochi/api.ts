import { apiGet, apiPost } from '../../api/client'

export type PetType = 'cat' | 'dog' | 'pokemon' | 'capybara' | 'alien'
export type ActionType = 'feed' | 'play' | 'sleep' | 'wake' | 'move_to'

export type Vec2 = { x: number; y: number }

export type PetState = {
  pet_id: string
  type: PetType
  alive: boolean
  is_sleeping: boolean
  pos: Vec2
  target?: Vec2 | null
  stats: { hp: number; hunger: number; sleepiness: number; mood: number }
  last_update_at?: string
  activity?: string
}

export async function tamagochiMe(token: string): Promise<{ pet: PetState | null; neglect?: any }> {
  return apiGet('/tamagochi/me', token)
}

export async function tamagochiAdopt(
  token: string,
  type: PetType,
  petName?: string,
): Promise<{ ok: boolean; pet: PetState }> {
  const body: Record<string, unknown> = { type }
  if (petName?.trim()) body.pet_name = petName.trim().slice(0, 32)
  return apiPost('/tamagochi/adopt', body, token)
}

export async function tamagochiStatus(token: string): Promise<{ needs_attention: boolean; reason: string | null }> {
  return apiGet('/tamagochi/status', token)
}

export async function tamagochiHistory(token: string): Promise<{ history: unknown[] }> {
  return apiGet('/tamagochi/history', token)
}

export async function tamagochiRecreate(
  token: string,
  type: PetType,
  petName?: string,
): Promise<{ ok: boolean; pet: PetState }> {
  const body: Record<string, unknown> = { type }
  if (petName?.trim()) body.pet_name = petName.trim().slice(0, 32)
  return apiPost('/tamagochi/recreate', body, token)
}

export async function tamagochiAction(
  token: string,
  type: ActionType,
  payload?: Record<string, any> | null
): Promise<{ ok: boolean; pet: PetState; neglect?: any }> {
  return apiPost('/tamagochi/action', { type, payload: payload ?? null }, token)
}

export async function tamagochiEndVisit(token: string): Promise<{ ok: boolean; alive?: boolean }> {
  return apiPost('/tamagochi/end_visit', {}, token)
}

export async function tamagochiShop(token: string): Promise<any> {
  return apiGet('/tamagochi/shop', token)
}

export async function tamagochiExchange(token: string, diamonds: number): Promise<any> {
  return apiPost('/tamagochi/exchange', { diamonds }, token)
}

export async function tamagochiBuy(
  token: string,
  item: 'food' | 'toy',
  qty: number,
  foodFor?: PetType
): Promise<any> {
  const body: Record<string, unknown> = { item, qty }
  if (item === 'food') {
    if (!foodFor) throw new Error('foodFor required for food')
    body.food_for = foodFor
  }
  return apiPost('/tamagochi/buy', body, token)
}

export async function tamagochiHealCoins(token: string): Promise<{
  ok: boolean
  pet: PetState
  wallet: { coins: number; diamonds: number }
}> {
  return apiPost('/tamagochi/heal_coins', {}, token)
}
