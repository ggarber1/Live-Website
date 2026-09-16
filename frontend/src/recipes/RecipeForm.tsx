import { useState, type FormEvent } from 'react'

import { fromLines, toLines } from '../lines'
import type { RecipeDraft } from './api'

interface Props {
  initial?: RecipeDraft
  onSubmit: (draft: RecipeDraft) => void
  busy?: boolean
}

export default function RecipeForm({ initial, onSubmit, busy = false }: Props) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [ingredients, setIngredients] = useState(toLines(initial?.ingredients ?? []))
  const [instructions, setInstructions] = useState(toLines(initial?.instructions ?? []))
  const [problem, setProblem] = useState<string | null>(null)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      setProblem('A recipe needs a title.')
      return
    }
    setProblem(null)
    onSubmit({
      title: title.trim(),
      ingredients: fromLines(ingredients),
      instructions: fromLines(instructions),
    })
  }

  return (
    <form className="stack" onSubmit={submit}>
      {problem && <p role="alert">{problem}</p>}
      <label>
        <span className="label">Title</span>
        <input className="field" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        <span className="label">Ingredients <em>one per line</em></span>
        <textarea className="field" rows={6} value={ingredients} onChange={(e) => setIngredients(e.target.value)} />
      </label>
      <label>
        <span className="label">Method <em>one step per line</em></span>
        <textarea className="field" rows={8} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
      </label>
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>Save</button>
      </div>
    </form>
  )
}
