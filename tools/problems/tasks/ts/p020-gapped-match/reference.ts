export function gappedMatch(
  needle: string,
  haystack: string,
  gap: number,
): boolean {
  if (typeof needle !== "string" || needle.length === 0) {
    throw new Error("needle must be a non-empty string");
  }
  if (typeof gap !== "number" || !Number.isInteger(gap) || gap < 0) {
    throw new Error("gap must be a non-negative whole number");
  }
  const memo = new Map<number, boolean>();
  const can = (i: number, j: number): boolean => {
    if (haystack[j] !== needle[i]) {
      return false;
    }
    if (i === needle.length - 1) {
      return true;
    }
    const key = i * haystack.length + j;
    const seen = memo.get(key);
    if (seen !== undefined) {
      return seen;
    }
    let result = false;
    const limit = Math.min(j + 1 + gap, haystack.length - 1);
    for (let k = j + 1; k <= limit && !result; k++) {
      result = can(i + 1, k);
    }
    memo.set(key, result);
    return result;
  };
  for (let j = 0; j < haystack.length; j++) {
    if (can(0, j)) {
      return true;
    }
  }
  return false;
}
