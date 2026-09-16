const EXCERPT = 160

export function excerpt(content: string): string {
  const flat = content.replace(/\s+/g, ' ').trim()
  return flat.length > EXCERPT ? flat.slice(0, EXCERPT) + '…' : flat
}

export function paragraphs(content: string): string[] {
  return content.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
}
