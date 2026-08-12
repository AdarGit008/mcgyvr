/** The fewest stamps that make exact postage from given denominations. */

export function fewestStamps(
  postage: number,
  denominations: number[],
): { count: number; stamps: number[] } {
  if (!Number.isInteger(postage) || postage < 0) {
    throw new Error("postage must be a non-negative integer");
  }
  if (!Array.isArray(denominations) || denominations.length === 0) {
    throw new Error("denominations must be a non-empty list");
  }
  const seen = new Set<number>();
  for (const stamp of denominations) {
    if (!Number.isInteger(stamp) || stamp <= 0) {
      throw new Error("denominations must be positive integers");
    }
    if (seen.has(stamp)) {
      throw new Error("denominations must not repeat");
    }
    seen.add(stamp);
  }
  const unreached = postage + 1;
  const best: number[] = new Array(postage + 1).fill(unreached);
  best[0] = 0;
  for (let value = 1; value <= postage; value += 1) {
    for (const stamp of denominations) {
      if (stamp <= value && best[value - stamp] + 1 < best[value]) {
        best[value] = best[value - stamp] + 1;
      }
    }
  }
  if (best[postage] === unreached) {
    throw new Error("the postage cannot be made exactly");
  }
  const descending = [...denominations].sort((a, b) => b - a);
  const stamps: number[] = [];
  let value = postage;
  while (value > 0) {
    for (const stamp of descending) {
      if (stamp <= value && best[value - stamp] === best[value] - 1) {
        stamps.push(stamp);
        value -= stamp;
        break;
      }
    }
  }
  return { count: stamps.length, stamps };
}
