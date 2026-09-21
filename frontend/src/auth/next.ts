// Where the visit goes after logging in: back where it was headed, but only
// to a path on this site. Anything else is an open redirect.
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/'
  return raw
}
