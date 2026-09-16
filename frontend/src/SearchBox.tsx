import { useEffect, useState } from 'react'

const DEBOUNCE_MS = 300

interface Props {
  onChange: (query: string) => void
}

// Shows keystrokes immediately, reports them after a pause. Every value is
// reported, including the empty string: clearing the box is a search too.
export default function SearchBox({ onChange }: Props) {
  const [value, setValue] = useState('')
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (!dirty) return
    const timer = setTimeout(() => onChange(value), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [value, dirty, onChange])

  return (
    <input
      type="search"
      placeholder="Search title, artist or album"
      aria-label="Search"
      value={value}
      onChange={(e) => {
        setValue(e.target.value)
        setDirty(true)
      }}
    />
  )
}
