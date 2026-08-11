export function stepAllowed(
  from: string,
  to: string,
  allowed: string[][],
): boolean {
  for (const move of allowed) {
    if (move[0] === from && move[1] === to) {
      return true;
    }
  }
  return false;
}

export function stepPlan(states: string[], allowed: string[][]): number {
  if (states.length === 0) {
    throw new Error("a run needs at least one state");
  }
  for (let i = 1; i < states.length; i += 1) {
    if (!stepAllowed(states[i - 1], states[i], allowed)) {
      return i;
    }
  }
  return -1;
}
