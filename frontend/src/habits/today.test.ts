import { doneToday, streakLabel } from './today'

const now = new Date(2026, 8, 16, 9, 30) // 16 Sep 2026, local

describe('doneToday', () => {
  test('true when the stored date is today', () => {
    expect(doneToday('Wed, 16 Sep 2026 00:00:00 GMT', now)).toBe(true)
  })

  test('false for yesterday', () => {
    expect(doneToday('Tue, 15 Sep 2026 00:00:00 GMT', now)).toBe(false)
  })

  test('false when never completed', () => {
    expect(doneToday(null, now)).toBe(false)
  })
})

describe('streakLabel', () => {
  test.each([
    [0, 'no streak yet'],
    [1, '1 day'],
    [3, '3 days'],
  ])('%s -> %s', (streak, label) => {
    expect(streakLabel(streak)).toBe(label)
  })
})
