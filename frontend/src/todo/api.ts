import { json, request } from '../http'

export interface Todo {
  id: number
  task: string
  created_at: string
}

export function listTodos(): Promise<Todo[]> {
  return request('/api/todo')
}

export async function addTodo(task: string): Promise<number> {
  const { id } = await request<{ id: number }>('/api/todo', { method: 'POST', ...json({ task }) })
  return id
}

export function renameTodo(id: number, task: string): Promise<void> {
  return request(`/api/todo/${id}`, { method: 'PUT', ...json({ task }) })
}

export function removeTodo(id: number): Promise<void> {
  return request(`/api/todo/${id}`, { method: 'DELETE' })
}
