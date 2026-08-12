export function shedTail(text: string, piece: string): string {
  if (piece.length === 0) {
    return text;
  }
  let left = text;
  while (left.endsWith(piece)) {
    left = left.slice(0, left.length - piece.length);
  }
  return left;
}
