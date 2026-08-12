export function fontClamp(
  size: number,
  smallest: number,
  largest: number,
): number {
  if (smallest > largest) {
    throw new Error("range is inverted");
  }
  if (size < smallest) {
    return smallest;
  }
  return size > largest ? largest : size;
}
