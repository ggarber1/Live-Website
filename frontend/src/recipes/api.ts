import { json, request } from '../http'

export interface RecipeDraft {
  title: string
  ingredients: string[]
  instructions: string[]
}

export interface Recipe extends RecipeDraft {
  id: number
  created_at: string
}

export function listRecipes(): Promise<Recipe[]> {
  return request('/api/recipes')
}

// There is no GET /api/recipes/<id>; the list is small, so find it there.
export async function getRecipe(id: number): Promise<Recipe> {
  const found = (await listRecipes()).find((r) => r.id === id)
  if (!found) throw new Error(`no recipe with id ${id}`)
  return found
}

export async function createRecipe(draft: RecipeDraft): Promise<number> {
  const { id } = await request<{ id: number }>('/api/recipes', { method: 'POST', ...json(draft) })
  return id
}

export function updateRecipe(id: number, draft: RecipeDraft): Promise<void> {
  return request(`/api/recipes/${id}`, { method: 'PUT', ...json(draft) })
}

export function removeRecipe(id: number): Promise<void> {
  return request(`/api/recipes/${id}`, { method: 'DELETE' })
}
