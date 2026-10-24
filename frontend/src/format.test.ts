import { describe as describeTrack, formatDate, formatDuration, formatLocalDate, formatRuntime } from './format'
import type { Track } from './music/api'

const base: Track = {
  id: 1, title: 't', artist: null, album: null, track_no: null,
  duration_seconds: null, format: 'mp3', size_bytes: 1, created_at: '',
}

describe('formatDuration', () => {
  test.each([
    [0, '0:00'],
    [65, '1:05'],
    [3725, '1:02:05'],
    [null, ''],
  ])('%s -> %s', (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected)
  })
})

describe('describe', () => {
  test('joins artist and album', () => {
    expect(describeTrack({ ...base, artist: 'Synth', album: 'Demo' })).toBe('Synth — Demo')
  })

  test('drops whichever is missing', () => {
    expect(describeTrack({ ...base, artist: 'Synth' })).toBe('Synth')
    expect(describeTrack({ ...base, album: 'Demo' })).toBe('Demo')
  })

  test('is empty when both are missing', () => {
    expect(describeTrack(base)).toBe('')
  })
})

describe('formatDate', () => {
  test('renders the API timestamp as a readable date', () => {
    expect(formatDate('Tue, 15 Sep 2026 20:47:44 GMT')).toBe('15 September 2026')
  })

  test('keeps the labelled day for a late-night wall-clock time', () => {
    expect(formatDate('Sat, 24 Oct 2026 01:30:00 GMT')).toBe('24 October 2026')
  })
})

describe('formatLocalDate', () => {
  test('a post written at 10pm Eastern is dated that day, not the next', () => {
    expect(formatLocalDate('Sat, 24 Oct 2026 02:06:02 GMT', 'America/New_York')).toBe('23 October 2026')
  })

  test('the date turns over at midnight where the viewer is', () => {
    expect(formatLocalDate('Sat, 24 Oct 2026 04:00:00 GMT', 'America/New_York')).toBe('24 October 2026')
  })

  test("defaults to the viewer's own time zone", () => {
    const moment = 'Wed, 16 Sep 2026 12:00:00 GMT'
    expect(formatLocalDate(moment)).toBe(new Date(moment).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'long', year: 'numeric',
    }))
  })
})

describe('formatRuntime', () => {
  test.each([
    [6120, '1h 42m'],
    [2880, '48m'],
    [7200, '2h 0m'],
    [null, ''],
  ])('%s -> %s', (seconds, expected) => {
    expect(formatRuntime(seconds)).toBe(expected)
  })
})
