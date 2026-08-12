export function lapBest(laps: number[]): number {
  let best = 0;
  for (const lap of laps) {
    if (lap > 0 && (best === 0 || lap < best)) {
      best = lap;
    }
  }
  return best;
}
