// The home page greets Liv a different way each visit, cycling through
// Greg's list in order so it never repeats twice running. The place in the
// cycle is kept in the browser; without storage it falls back to the day.

export const GREETINGS = [
  'Hey Cutie Patootie',
  'What Up Shotayy',
  'BABY GIIIIRRRLLLLL',
  "'Ello Love",
  'Hi Darling',
  'Uhhhhhhhm Hi :)',
  'Yo.',
]

const LINES = [
  'What are we up to today?',
  'Tea first. Then the list.',
  'No rush on any of it.',
  "Let's see what's on.",
  'Something small today, maybe.',
  'The fern says hello.',
  'Whatever today turns into.',
]

const KEY = 'livs-greeting'

function dayOfYear(now: Date): number {
  const start = new Date(now.getFullYear(), 0, 0)
  return Math.floor((now.getTime() - start.getTime()) / 86_400_000)
}

export function nextGreeting(now: Date = new Date()): string {
  let index: number
  try {
    index = Number(localStorage.getItem(KEY) ?? '0') || 0
    localStorage.setItem(KEY, String((index + 1) % GREETINGS.length))
  } catch {
    index = dayOfYear(now)
  }
  return GREETINGS[index % GREETINGS.length]
}

export function dateLine(now: Date): string {
  const weekday = now.toLocaleDateString('en-GB', { weekday: 'long' })
  const day = now.getDate()
  const month = now.toLocaleDateString('en-GB', { month: 'long' })
  return `It's ${weekday}, ${day} ${month}.`
}

export function noteOfTheDay(now: Date): string {
  return LINES[dayOfYear(now) % LINES.length]
}
