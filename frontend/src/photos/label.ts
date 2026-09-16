import { formatDate } from '../format'
import type { Photo } from './api'

// What a print is called when spoken of: its caption, or failing that its date.
export function label(photo: Photo): string {
  return photo.caption || formatDate(photo.taken_at)
}
