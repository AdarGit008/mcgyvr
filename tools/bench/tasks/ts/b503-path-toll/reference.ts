export function stepCost(kind: string): number {
  if (kind === "hill") {
    return 5;
  }
  if (kind === "flat") {
    return 2;
  }
  return 3;
}

/** The path totalled, with every third step free. */
export function pathToll(steps: string[]): number {
  let total = 0;
  for (let i = 0; i < steps.length; i += 1) {
    if ((i + 1) % 3 !== 0) {
      total += stepCost(steps[i]);
    }
  }
  return total;
}
