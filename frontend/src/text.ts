// Plain text with blank-line paragraphs, as the blog and film overviews use.
export function paragraphs(content: string): string[] {
  return content.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
}
