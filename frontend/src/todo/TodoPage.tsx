import { useEffect, useState, type FormEvent } from 'react'

import InlineEdit from '../InlineEdit'

import { addTodo, listTodos, removeTodo, renameTodo, type Todo } from './api'

export default function TodoPage() {
  const [todos, setTodos] = useState<Todo[] | null>(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [leaving, setLeaving] = useState<Set<number>>(new Set())

  useEffect(() => {
    listTodos().then(setTodos, (err: Error) => setError(err.message))
  }, [])

  const add = async (e: FormEvent) => {
    e.preventDefault()
    const task = draft.trim()
    if (!task) return
    try {
      const id = await addTodo(task)
      setTodos((t) => [...(t ?? []), { id, task, created_at: '' }])
      setDraft('')
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  // The row stays, fading, until the server has agreed it is gone.
  const finish = async (id: number) => {
    setLeaving((s) => new Set(s).add(id))
    try {
      await removeTodo(id)
      setTodos((t) => (t ?? []).filter((todo) => todo.id !== id))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLeaving((s) => {
        const next = new Set(s)
        next.delete(id)
        return next
      })
    }
  }

  const rename = async (id: number, task: string) => {
    try {
      await renameTodo(id, task)
      setTodos((t) => (t ?? []).map((todo) => (todo.id === id ? { ...todo, task } : todo)))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <>
      <h1>To-do</h1>
      <p className="subtitle">Little things, crossed off one by one.</p>
      {error && <p role="alert">{error}</p>}
      <div className="card">
        <form className="add-row" onSubmit={add}>
          <input
            className="field"
            aria-label="New task"
            placeholder="Something to do…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" className="btn btn-primary">Add</button>
        </form>
        {todos && todos.length === 0 && <p className="empty">Nothing to do. Lovely.</p>}
        {todos && todos.length > 0 && (
          <ul className="todo-list">
            {todos.map((todo) => (
              <TodoRow
                key={todo.id}
                todo={todo}
                leaving={leaving.has(todo.id)}
                onFinish={() => finish(todo.id)}
                onRename={(task) => rename(todo.id, task)}
              />
            ))}
          </ul>
        )}
      </div>
    </>
  )
}

interface RowProps {
  todo: Todo
  leaving: boolean
  onFinish: () => void
  onRename: (task: string) => void
}

function TodoRow({ todo, leaving, onFinish, onRename }: RowProps) {
  return (
    <li className={leaving ? 'leaving' : undefined}>
      <button
        type="button"
        className="check"
        aria-label={`Done: ${todo.task}`}
        disabled={leaving}
        onClick={onFinish}
      />
      <InlineEdit value={todo.task} label="Task" onSave={onRename} />
    </li>
  )
}
