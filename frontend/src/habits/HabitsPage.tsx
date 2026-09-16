import { useEffect, useState, type FormEvent } from 'react'

import InlineEdit from '../InlineEdit'
import { addHabit, completeHabit, listHabits, removeHabit, renameHabit, type Habit } from './api'
import { doneToday, streakLabel } from './today'

export default function HabitsPage() {
  const [habits, setHabits] = useState<Habit[] | null>(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listHabits().then(setHabits, (err: Error) => setError(err.message))
  }, [])

  // Every mutation follows the same shape: call, patch local state, clear the
  // error; or show the error and leave the list as it was.
  const attempt = async (action: () => Promise<void>) => {
    try {
      await action()
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const add = (e: FormEvent) => {
    e.preventDefault()
    const name = draft.trim()
    if (!name) return
    attempt(async () => {
      const id = await addHabit(name)
      setHabits((h) => [...(h ?? []), { id, name, streak: 0, last_completed: null, created_at: '' }])
      setDraft('')
    })
  }

  const complete = (id: number) =>
    attempt(async () => {
      const updated = await completeHabit(id)
      setHabits((h) => (h ?? []).map((habit) => (habit.id === id ? updated : habit)))
    })

  const rename = (id: number, name: string) =>
    attempt(async () => {
      await renameHabit(id, name)
      setHabits((h) => (h ?? []).map((habit) => (habit.id === id ? { ...habit, name } : habit)))
    })

  const remove = (habit: Habit) => {
    if (!confirm(`Remove "${habit.name}"? Its streak goes with it.`)) return
    attempt(async () => {
      await removeHabit(habit.id)
      setHabits((h) => (h ?? []).filter((other) => other.id !== habit.id))
    })
  }

  return (
    <>
      <h1>Habits</h1>
      <p className="subtitle">Small promises, kept daily.</p>
      {error && <p role="alert">{error}</p>}
      <div className="card">
        <form className="add-row" onSubmit={add}>
          <input
            className="field"
            aria-label="New habit"
            placeholder="Something to keep up…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" className="btn btn-primary">Add</button>
        </form>
        {habits && habits.length === 0 && <p className="empty">No habits yet.</p>}
        {habits && habits.length > 0 && (
          <ul className="habit-list">
            {habits.map((habit) => {
              const done = doneToday(habit.last_completed)
              return (
                <li key={habit.id}>
                  <div className="habit-name">
                    <InlineEdit value={habit.name} label="Habit" onSave={(name) => rename(habit.id, name)} />
                    <div className="describe">{streakLabel(habit.streak)}</div>
                  </div>
                  <button
                    type="button"
                    className={done ? 'btn btn-done' : 'btn'}
                    disabled={done}
                    onClick={() => complete(habit.id)}
                  >
                    {done ? 'Done ✓' : 'Done today'}
                  </button>
                  <button type="button" className="btn btn-quiet btn-danger" onClick={() => remove(habit)}>
                    remove
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </>
  )
}
