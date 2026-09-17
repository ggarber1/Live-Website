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

export const NOTES = [
  'What are we up to today?',
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

// Liv's birthday: 27 September. That day the note is not on the rota.
const BIRTHDAY = { month: 8, day: 27 } // months are zero-based

export function isBirthday(now: Date): boolean {
  return now.getMonth() === BIRTHDAY.month && now.getDate() === BIRTHDAY.day
}

export function noteOfTheDay(now: Date): string {
  if (isBirthday(now)) return 'Happy Birthdayyy!!!'
  return NOTES[dayOfYear(now) % NOTES.length]
}
