import { json, request } from '../http'

export interface Habit {
  id: number
  name: string
  streak: number
  last_completed: string | null
  created_at: string
}

export function listHabits(): Promise<Habit[]> {
  return request('/api/habits')
}

export async function addHabit(name: string): Promise<number> {
  const { id } = await request<{ id: number }>('/api/habits', { method: 'POST', ...json({ name }) })
  return id
}

export function renameHabit(id: number, name: string): Promise<void> {
  return request(`/api/habits/${id}`, { method: 'PUT', ...json({ name }) })
}

export function removeHabit(id: number): Promise<void> {
  return request(`/api/habits/${id}`, { method: 'DELETE' })
}

export function completeHabit(id: number): Promise<Habit> {
  return request(`/api/habits/${id}/complete`, { method: 'POST' })
}
