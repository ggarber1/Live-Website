// Textareas hold one item per line; the API wants arrays of strings.
export function toLines(items: string[]): string {
  return items.join('\n')
}

export function fromLines(text: string): string[] {
  return text.split('\n').map((line) => line.trim()).filter(Boolean)
}
