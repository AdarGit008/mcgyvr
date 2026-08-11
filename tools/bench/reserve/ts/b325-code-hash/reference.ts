export function codeHash(code: string, buckets: number): number {
  if (buckets <= 0) {
    throw new Error("buckets must be positive");
  }
  let total = 0;
  for (const letter of code.toLowerCase()) {
    if (letter >= "a" && letter <= "z") {
      total += letter.charCodeAt(0) - 96;
    }
  }
  return total % buckets;
}
