import { dateLine, GREETINGS, nextGreeting, noteOfTheDay } from './greeting'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('nextGreeting', () => {
  test('cycles through the whole list in order, then starts again', () => {
    const seen = Array.from({ length: GREETINGS.length + 1 }, () => nextGreeting())

    expect(seen.slice(0, GREETINGS.length)).toEqual(GREETINGS)
    expect(seen[GREETINGS.length]).toBe(GREETINGS[0])
  })

  test('the list is exactly what was asked for', () => {
    expect(GREETINGS).toEqual([
      'Hey Cutie Patootie', 'What Up Shotayy', 'BABY GIIIIRRRLLLLL', "'Ello Love",
      'Hi Darling', 'Uhhhhhhhm Hi :)', 'Yo.',
    ])
  })

  test('without storage it still greets, by the day', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } })

    expect(GREETINGS).toContain(nextGreeting(new Date(2026, 8, 16)))
    expect(nextGreeting(new Date(2026, 8, 16))).toBe(nextGreeting(new Date(2026, 8, 16)))
  })
})

test('the date line reads like speech', () => {
  expect(dateLine(new Date(2026, 8, 16, 9))).toBe("It's Wednesday, 16 September.")
})

test('the note changes with the day and repeats after the list', () => {
  const a = noteOfTheDay(new Date(2026, 8, 16))
  const b = noteOfTheDay(new Date(2026, 8, 17))
  expect(a).not.toBe(b)
  expect(noteOfTheDay(new Date(2026, 8, 23))).toBe(a)
})
