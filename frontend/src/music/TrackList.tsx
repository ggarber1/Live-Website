import type { Track } from './api'
import { describe, formatDuration } from '../format'

interface Props {
  tracks: Track[]
  total: number
  offset: number
  limit: number
  playingId: number | null
  onPlay: (track: Track) => void
  onPage: (offset: number) => void
}

export default function TrackList({ tracks, total, offset, limit, playingId, onPlay, onPage }: Props) {
  if (total === 0) return <p className="empty">No tracks</p>

  const first = offset + 1
  const last = Math.min(offset + limit, total)

  return (
    <>
      <table className="tracks">
        <thead>
          <tr>
            <th>Title</th>
            <th className="duration">Length</th>
          </tr>
        </thead>
        <tbody>
          {tracks.map((track) => (
            <tr
              key={track.id}
              aria-current={track.id === playingId ? 'true' : undefined}
              onClick={() => onPlay(track)}
            >
              <td>
                <button type="button" className="title">{track.title}</button>
                <div className="describe">{describe(track)}</div>
              </td>
              <td className="duration">{formatDuration(track.duration_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <nav className="pager" aria-label="Pages">
        <button type="button" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - limit))}>
          Previous
        </button>
        <span>{first}–{last} of {total}</span>
        <button type="button" disabled={last >= total} onClick={() => onPage(offset + limit)}>
          Next
        </button>
      </nav>
    </>
  )
}
