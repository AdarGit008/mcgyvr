/** A list with its first and last entries exchanged. */
export function swapEnds(items: string[]): string[] {
  if (items.length < 2) {
    return items;
  }
  const copied = [...items];
  const last = copied.length - 1;
  copied[0] = items[last];
  copied[last] = items[0];
  return copied;
}
