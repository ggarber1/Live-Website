const EXCERPT = 160

export function excerpt(content: string): string {
  const flat = content.replace(/\s+/g, ' ').trim()
  return flat.length > EXCERPT ? flat.slice(0, EXCERPT) + '…' : flat
}

export { paragraphs } from '../text'
