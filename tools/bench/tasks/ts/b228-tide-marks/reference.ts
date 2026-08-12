export function tideMarks(levels: number[]): number[] {
  const peaks: number[] = [];
  for (let i = 1; i < levels.length - 1; i += 1) {
    if (levels[i] > levels[i - 1] && levels[i] > levels[i + 1]) {
      peaks.push(i);
    }
  }
  return peaks;
}
