export function stepValue(step: string): number {
  if (step === "+") {
    return 1;
  }
  if (step === "-") {
    return -1;
  }
  return 0;
}

/** The running total after each instruction. */
export function scanTally(steps: string[]): number[] {
  const running: number[] = [];
  let total = 0;
  for (const step of steps) {
    total += stepValue(step);
    running.push(total);
  }
  return running;
}
