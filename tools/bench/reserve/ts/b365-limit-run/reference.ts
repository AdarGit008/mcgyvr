export function overLimit(reading: number, limit: number): boolean {
  return reading > limit;
}

export function limitRun(readings: number[], limit: number): number[] {
  const kept: number[] = [];
  for (const reading of readings) {
    if (overLimit(reading, limit)) {
      break;
    }
    kept.push(reading);
  }
  return kept;
}
