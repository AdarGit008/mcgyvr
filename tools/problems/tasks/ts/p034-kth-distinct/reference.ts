export function kthDistinct(values: number[], k: number): number {
  if (!Array.isArray(values) || values.some((v) => !Number.isInteger(v))) {
    throw new Error("values must be a list of integers");
  }
  if (values.length === 0) {
    throw new Error("values must not be empty");
  }
  if (!Number.isInteger(k) || k < 1) {
    throw new Error("k must be a positive integer");
  }
  const distinct = [...new Set(values)].sort((a, b) => a - b);
  if (k > distinct.length) {
    throw new Error("k exceeds the number of distinct values");
  }
  return distinct[k - 1];
}
