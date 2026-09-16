import '@testing-library/jest-dom/vitest'

// jsdom has no media pipeline: play() throws "not implemented". The Player
// tests are about wiring, so playback is a spy that resolves.
Object.defineProperty(HTMLMediaElement.prototype, 'play', {
  configurable: true,
  writable: true,
  value: vi.fn(() => Promise.resolve()),
})
Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
  configurable: true,
  writable: true,
  value: vi.fn(),
})
