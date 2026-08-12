export function parcelGirth(width: number, height: number): number {
  return 2 * (width + height);
}

export function parcelOversize(
  length: number,
  width: number,
  height: number,
  limit: number,
): boolean {
  return length + parcelGirth(width, height) > limit;
}
