// last_completed is a GMT date string at midnight (or null). It counts as
// today when its UTC calendar date is the viewer's local calendar date.
export function doneToday(lastCompleted: string | null, now: Date = new Date()): boolean {
  if (!lastCompleted) return false
  const d = new Date(lastCompleted)
  return (
    d.getUTCFullYear() === now.getFullYear() &&
    d.getUTCMonth() === now.getMonth() &&
    d.getUTCDate() === now.getDate()
  )
}

export function streakLabel(streak: number): string {
  if (streak <= 0) return 'no streak yet'
  return streak === 1 ? '1 day' : `${streak} days`
}
