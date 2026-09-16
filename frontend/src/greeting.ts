// "Good morning, Liv" and a small line that changes with the day, so the
// home page reads like a note left on the counter rather than a dashboard.

const LINES = [
  'What are we up to today?',
  'Tea first. Then the list.',
  'No rush on any of it.',
  "Let's see what's on.",
  'Something small today, maybe.',
  'The fern says hello.',
  'Whatever today turns into.',
]

export function greeting(now: Date): string {
  const h = now.getHours()
  if (h < 5) return 'Still up, Liv?'
  if (h < 12) return 'Good morning, Liv'
  if (h < 17) return 'Good afternoon, Liv'
  return 'Good evening, Liv'
}

export function dateLine(now: Date): string {
  const weekday = now.toLocaleDateString('en-GB', { weekday: 'long' })
  const day = now.getDate()
  const month = now.toLocaleDateString('en-GB', { month: 'long' })
  return `It's ${weekday}, ${day} ${month}.`
}

export function noteOfTheDay(now: Date): string {
  const start = new Date(now.getFullYear(), 0, 0)
  const dayOfYear = Math.floor((now.getTime() - start.getTime()) / 86_400_000)
  return LINES[dayOfYear % LINES.length]
}
