import { useState, type KeyboardEvent } from 'react'

interface Props {
  value: string
  label: string
  onSave: (value: string) => void
}

// Text with a quiet "edit" beside it. Editing turns it into a field: Enter
// saves (if changed and not blank), Escape or leaving the field cancels.
export default function InlineEdit({ value, label, onSave }: Props) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(value)

  const cancel = () => {
    setText(value)
    setEditing(false)
  }

  const keys = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const next = text.trim()
      if (next && next !== value) onSave(next)
      setEditing(false)
    } else if (e.key === 'Escape') {
      cancel()
    }
  }

  if (editing) {
    return (
      <input
        className="field inline-field"
        aria-label={label}
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={keys}
        onBlur={cancel}
      />
    )
  }
  return (
    <>
      <span className="inline-text">{value}</span>
      <button type="button" className="btn btn-quiet" onClick={() => { setText(value); setEditing(true) }}>
        edit
      </button>
    </>
  )
}
