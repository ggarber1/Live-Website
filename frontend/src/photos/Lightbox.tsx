import { useEffect } from 'react'

import { formatDate } from '../format'
import InlineEdit from '../InlineEdit'
import { removePhoto, setCaption, thumbUrl, type Photo } from './api'
import { label } from './label'

interface Props {
  photos: Photo[]
  index: number
  onClose: () => void
  onIndex: (index: number) => void
  onCaption: (id: number, caption: string) => void
  onRemove: (id: number) => void
}

export default function Lightbox({ photos, index, onClose, onIndex, onCaption, onRemove }: Props) {
  const photo = photos[index]
  const hasPrev = index > 0
  const hasNext = index < photos.length - 1

  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight' && hasNext) onIndex(index + 1)
      else if (e.key === 'ArrowLeft' && hasPrev) onIndex(index - 1)
    }
    window.addEventListener('keydown', keys)
    return () => window.removeEventListener('keydown', keys)
  }, [index, hasPrev, hasNext, onClose, onIndex])

  const save = async (caption: string) => {
    await setCaption(photo.id, caption)
    onCaption(photo.id, caption)
  }

  const remove = async () => {
    if (!confirm('Delete this photo? It comes off the drive too.')) return
    await removePhoto(photo.id)
    onRemove(photo.id)
  }

  return (
    <div className="lightbox" role="dialog" aria-label={label(photo)}>
      <button type="button" className="lightbox-close" aria-label="Close" onClick={onClose}>×</button>
      <button type="button" className="lightbox-nav prev" aria-label="Previous" disabled={!hasPrev} onClick={() => onIndex(index - 1)}>‹</button>
      <div className="lightbox-frame">
        <img src={thumbUrl(photo.id, 1200)} alt={label(photo)} />
        <div className="lightbox-caption">
          <InlineEdit value={photo.caption ?? ''} label="Caption" onSave={save} />
          <span className="describe">{formatDate(photo.taken_at)}</span>
          <button type="button" className="btn btn-quiet btn-danger" onClick={remove}>delete</button>
        </div>
      </div>
      <button type="button" className="lightbox-nav next" aria-label="Next" disabled={!hasNext} onClick={() => onIndex(index + 1)}>›</button>
    </div>
  )
}
