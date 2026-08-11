export function tagOpen(marker: string): string {
  if (!marker.startsWith("<") || !marker.endsWith(">")) {
    throw new Error("marker must be bracketed");
  }
  const inner = marker.slice(1, -1);
  return inner.startsWith("/") ? inner.slice(1) : inner;
}

export function tagPair(opening: string, closing: string): boolean {
  return tagOpen(opening) === tagOpen(closing);
}
