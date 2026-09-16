import { dateLine, greeting, noteOfTheDay } from './greeting'

describe('greeting', () => {
  test.each([
    [3, 'Still up, Liv?'],
    [8, 'Good morning, Liv'],
    [13, 'Good afternoon, Liv'],
    [20, 'Good evening, Liv'],
  ])('at %s o\'clock: %s', (hour, expected) => {
    expect(greeting(new Date(2026, 8, 16, hour))).toBe(expected)
  })
})

test('the date line reads like speech', () => {
  expect(dateLine(new Date(2026, 8, 16, 9))).toBe("It's Wednesday, 16 September.")
})

test('the note changes with the day and repeats after the list', () => {
  const a = noteOfTheDay(new Date(2026, 8, 16))
  const b = noteOfTheDay(new Date(2026, 8, 17))
  const again = noteOfTheDay(new Date(2026, 8, 23))
  expect(a).not.toBe(b)
  expect(again).toBe(a)
})
