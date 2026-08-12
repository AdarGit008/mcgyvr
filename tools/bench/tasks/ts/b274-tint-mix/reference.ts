export function tintMix(
  volumeA: number,
  strengthA: number,
  volumeB: number,
  strengthB: number,
): number {
  const total = volumeA + volumeB;
  if (total === 0) {
    return 0;
  }
  return Math.floor((volumeA * strengthA + volumeB * strengthB) / total);
}
