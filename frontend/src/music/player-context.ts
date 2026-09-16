import { createContext, useContext } from 'react'

import type { Track } from './api'

export interface PlayerApi {
  playing: Track | null
  play: (tracks: Track[], index: number) => void
}

export const PlayerContext = createContext<PlayerApi | null>(null)

export function usePlayer(): PlayerApi {
  const api = useContext(PlayerContext)
  if (!api) throw new Error('usePlayer needs a PlayerProvider above it')
  return api
}
