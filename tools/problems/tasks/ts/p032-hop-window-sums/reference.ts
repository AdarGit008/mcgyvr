export function hopWindowSums(values: number[], size: number, hop: number): number[] {
  if (!Array.isArray(values) || values.some((v) => !Number.isInteger(v))) {
    throw new Error("values must be a list of integers");
  }
  if (!Number.isInteger(size) || size < 1) {
    throw new Error("size must be a positive integer");
  }
  if (!Number.isInteger(hop) || hop < 1) {
    throw new Error("hop must be a positive integer");
  }
  const sums: number[] = [];
  for (let start = 0; start + size <= values.length; start += hop) {
    let total = 0;
    for (let i = start; i < start + size; i++) {
      total += values[i];
    }
    sums.push(total);
  }
  return sums;
}
