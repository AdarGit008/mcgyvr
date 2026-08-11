export function anyOver(readings: number[], level: number): boolean {
  for (const reading of readings) {
    if (reading > level) {
      return true;
    }
  }
  return false;
}

export function windowAny(
  readings: number[],
  width: number,
  level: number,
): boolean[] {
  const answers: boolean[] = [];
  for (let i = 0; i + width <= readings.length; i += 1) {
    answers.push(anyOver(readings.slice(i, i + width), level));
  }
  return answers;
}
