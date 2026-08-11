export function enterCount(states: string[], wanted: string): number {
  let entries = 0;
  for (let i = 0; i < states.length; i += 1) {
    if (states[i] === wanted && (i === 0 || states[i - 1] !== wanted)) {
      entries += 1;
    }
  }
  return entries;
}
