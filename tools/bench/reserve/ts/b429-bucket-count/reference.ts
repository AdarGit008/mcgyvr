export function bucketCount(
  readings: number[],
  width: number,
): Record<number, number> {
  const buckets: Record<number, number> = {};
  for (const reading of readings) {
    const low = Math.floor(reading / width) * width;
    buckets[low] = (buckets[low] ?? 0) + 1;
  }
  return buckets;
}
