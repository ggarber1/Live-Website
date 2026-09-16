import { describe as describeTrack, formatDate, formatDuration } from './format'
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
})
