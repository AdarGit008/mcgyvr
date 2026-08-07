export function minimaxPairSum(first: number[], second: number[]): number {
  if (!Array.isArray(first) || !Array.isArray(second)) {
    throw new Error("expected two arrays of integers");
  }
  if (first.length === 0 || second.length === 0) {
    throw new Error("lists must be non-empty");
  }
  if (first.length !== second.length) {
    throw new Error("lists must have equal length");
  }
  for (const values of [first, second]) {
    for (const value of values) {
      if (!Number.isInteger(value)) {
        throw new Error("entries must be integers");
      }
    }
  }
  const rising = [...first].sort((a, b) => a - b);
  const falling = [...second].sort((a, b) => b - a);
  let worst = rising[0] + falling[0];
  for (let i = 1; i < rising.length; i++) {
    const sum = rising[i] + falling[i];
    if (sum > worst) {
      worst = sum;
    }
  }
  return worst;
}
