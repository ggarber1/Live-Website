import { thumbUrl, type Photo } from './api'
import { label } from './label'

interface Props {
  photo: Photo
  onOpen?: () => void
  tilt?: number
}

// A print in a white frame with a line written beneath it.
export default function Polaroid({ photo, onOpen, tilt = 0 }: Props) {
  const inner = (
    <figure className="polaroid" style={tilt ? { transform: `rotate(${tilt}deg)` } : undefined}>
      <img src={thumbUrl(photo.id, 400)} alt={label(photo)} loading="lazy" />
      <figcaption>{label(photo)}</figcaption>
    </figure>
  )
  if (!onOpen) return inner
  return (
    <button type="button" className="polaroid-button" onClick={onOpen}>
      {inner}
    </button>
  )
}
