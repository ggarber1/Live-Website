import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { usePlayer } from './player-context'
import { PlayerProvider } from './queue'

const track = {
  id: 1, title: 'Track 1', artist: 'Synth', album: 'Demo', track_no: 1,
  duration_seconds: 65, format: 'mp3', size_bytes: 1, created_at: '',
}

function Consumer() {
  const { play, pause } = usePlayer()
  return (
    <>
      <button onClick={() => play([track], 0)}>start</button>
      <button onClick={pause}>pause</button>
    </>
  )
}

test('pause() pauses the audio element the bar is playing', async () => {
  const pauseSpy = HTMLMediaElement.prototype.pause as ReturnType<typeof vi.fn>
  pauseSpy.mockClear()
  render(<PlayerProvider><Consumer /></PlayerProvider>)

  await userEvent.click(screen.getByText('start'))
  expect(document.querySelector('audio')).not.toBeNull()
  await userEvent.click(screen.getByText('pause'))

  expect(pauseSpy).toHaveBeenCalledTimes(1)
})

test('pause() with nothing playing is a no-op', async () => {
  const pauseSpy = HTMLMediaElement.prototype.pause as ReturnType<typeof vi.fn>
  pauseSpy.mockClear()
  render(<PlayerProvider><Consumer /></PlayerProvider>)

  await userEvent.click(screen.getByText('pause'))

  expect(pauseSpy).not.toHaveBeenCalled()
})
