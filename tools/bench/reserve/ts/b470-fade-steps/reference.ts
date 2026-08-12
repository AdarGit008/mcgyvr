export function fadeSteps(level: number): number[] {
  const run: number[] = [];
  let current = level;
  while (current > 0) {
    run.push(current);
    current = Math.floor(current / 2);
  }
  return run;
}
