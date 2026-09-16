import { json, request } from '../http'

export interface PostDraft {
  title: string
  content: string
}

export interface Post extends PostDraft {
  id: number
  created_at: string
}

export function listPosts(): Promise<Post[]> {
  return request('/api/blog')
}

export async function getPost(id: number): Promise<Post> {
  const found = (await listPosts()).find((p) => p.id === id)
  if (!found) throw new Error(`no post with id ${id}`)
  return found
}

export async function createPost(draft: PostDraft): Promise<number> {
  const { id } = await request<{ id: number }>('/api/blog', { method: 'POST', ...json(draft) })
  return id
}

export function updatePost(id: number, draft: PostDraft): Promise<void> {
  return request(`/api/blog/${id}`, { method: 'PUT', ...json(draft) })
}

export function removePost(id: number): Promise<void> {
  return request(`/api/blog/${id}`, { method: 'DELETE' })
}
