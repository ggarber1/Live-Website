import { act, render } from '@testing-library/react'

import VideoPlayer from './VideoPlayer'

// vi.mock is hoisted above imports, so the fake must be hoisted with it.
const { FakeHls, instances } = vi.hoisted(() => {
  const instances: FakeHls[] = []
  class FakeHls {
    static isSupported = () => true
    static Events = { ERROR: 'hlsError' }
    handlers: Record<string, (e: string, data: unknown) => void> = {}
    loadSource = vi.fn()
    attachMedia = vi.fn()
    destroy = vi.fn()
    on = vi.fn((event: string, handler: (e: string, data: unknown) => void) => { this.handlers[event] = handler })
    constructor() { instances.push(this) }
  }
  return { FakeHls, instances }
})
vi.mock('hls.js', () => ({ default: FakeHls }))

const HLS_URL = 'http://localhost:5000/api/cinema/videos/x/master.m3u8?a=1'

function video(): HTMLVideoElement {
  return document.querySelector('video')!
}

const spyCanPlay = () => vi.spyOn(HTMLMediaElement.prototype, 'canPlayType')
let canPlay: ReturnType<typeof spyCanPlay>
beforeEach(() => {
  instances.length = 0
  canPlay = spyCanPlay().mockReturnValue('')
})
afterEach(() => canPlay.mockRestore())

test('direct play sets the source on the video element', () => {
  render(<VideoPlayer kind="direct" url="/api/cinema/films/a/file" onStop={() => {}} />)

  expect(video()).toHaveAttribute('src', 'http://localhost:5000/api/cinema/films/a/file')
  expect(instances).toHaveLength(0)
})

test('hls on a browser without native support goes through hls.js', () => {
  render(<VideoPlayer kind="hls" url="/api/cinema/videos/x/master.m3u8?a=1" onStop={() => {}} />)

  expect(instances).toHaveLength(1)
  expect(instances[0].loadSource).toHaveBeenCalledWith(HLS_URL)
  expect(instances[0].attachMedia).toHaveBeenCalledWith(video())
  expect(video()).not.toHaveAttribute('src')
})

test('hls on Safari uses the native player and not hls.js', () => {
  canPlay.mockReturnValue('maybe')
  render(<VideoPlayer kind="hls" url="/api/cinema/videos/x/master.m3u8?a=1" onStop={() => {}} />)

  expect(instances).toHaveLength(0)
  expect(video()).toHaveAttribute('src', HLS_URL)
})

test('unmounting destroys hls.js and reports the stop', () => {
  const onStop = vi.fn()
  const { unmount } = render(<VideoPlayer kind="hls" url="/api/cinema/videos/x/master.m3u8" onStop={onStop} />)

  unmount()

  expect(instances[0].destroy).toHaveBeenCalledTimes(1)
  expect(onStop).toHaveBeenCalledTimes(1)
})

test('leaving the page reports the stop too', () => {
  const onStop = vi.fn()
  render(<VideoPlayer kind="direct" url="/api/cinema/films/a/file" onStop={onStop} />)

  window.dispatchEvent(new Event('pagehide'))

  expect(onStop).toHaveBeenCalledTimes(1)
})

test('a fatal hls error shows one line under the video', () => {
  const { getByRole } = render(<VideoPlayer kind="hls" url="/api/cinema/videos/x/master.m3u8" onStop={() => {}} />)

  act(() => instances[0].handlers['hlsError']('hlsError', { fatal: true, details: 'manifestLoadError' }))

  expect(getByRole('alert')).toHaveTextContent(/manifestLoadError/)
})
