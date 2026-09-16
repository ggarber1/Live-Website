import { useEffect, useRef, useState } from 'react'

import { listPhotos, uploadPhotos, type Photo } from './api'
import Lightbox from './Lightbox'
import Polaroid from './Polaroid'

export default function PhotosPage() {
  const [photos, setPhotos] = useState<Photo[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listPhotos().then((page) => setPhotos(page.photos), (err: Error) => setError(err.message))
  }, [])

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setBusy(true)
    setNotice(null)
    try {
      const result = await uploadPhotos(Array.from(files))
      setPhotos((p) => [...result.added, ...(p ?? [])])
      if (result.rejected.length) {
        setNotice(result.rejected.map((r) => `${r.name}: ${r.reason}`).join('. '))
      }
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  const list = photos ?? []
  return (
    <>
      <div className="title-row">
        <div>
          <h1>Photos</h1>
          <p className="subtitle">Kept for looking back on.</p>
        </div>
        <label className="btn btn-primary upload">
          {busy ? 'Adding…' : 'Add photos'}
          <input
            ref={input}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            multiple
            aria-label="Add photos"
            disabled={busy}
            onChange={(e) => upload(e.target.files)}
          />
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="alert" className="notice">{notice}</p>}
      {photos && photos.length === 0 && <p className="empty">No photos yet.</p>}
      {list.length > 0 && (
        <div className="photo-grid">
          {list.map((photo, i) => (
            <Polaroid key={photo.id} photo={photo} onOpen={() => setOpen(i)} />
          ))}
        </div>
      )}
      {open !== null && list[open] && (
        <Lightbox
          photos={list}
          index={open}
          onClose={() => setOpen(null)}
          onIndex={setOpen}
          onCaption={(id, caption) =>
            setPhotos((p) => (p ?? []).map((ph) => (ph.id === id ? { ...ph, caption: caption || null } : ph)))}
          onRemove={(id) => {
            setPhotos((p) => (p ?? []).filter((ph) => ph.id !== id))
            setOpen(null)
          }}
        />
      )}
    </>
  )
}
