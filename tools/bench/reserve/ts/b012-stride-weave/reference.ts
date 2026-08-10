function checkStride(items: number[], step: number, offset: number): void {
  if (!Array.isArray(items)) {
    throw new Error("items must be a list");
  }
  if (!Number.isInteger(step) || step < 1) {
    throw new Error("step must be a positive integer");
  }
  if (!Number.isInteger(offset) || offset < 0 || offset >= step) {
    throw new Error("offset must be an integer in [0, step)");
  }
}

export function strideTake(
  items: number[],
  step: number,
  offset: number,
): number[] {
  checkStride(items, step, offset);
  return items.filter((_, index) => index % step === offset);
}

export function strideSkip(
  items: number[],
  step: number,
  offset: number,
): number[] {
  checkStride(items, step, offset);
  return items.filter((_, index) => index % step !== offset);
}

export function strideWeave(parts: number[][]): number[] {
  if (!Array.isArray(parts)) {
    throw new Error("parts must be a list");
  }
  for (const part of parts) {
    if (!Array.isArray(part)) {
      throw new Error("every part must be a list");
    }
  }
  const woven: number[] = [];
  const cursors = parts.map(() => 0);
  let remaining = parts.reduce((total, part) => total + part.length, 0);
  while (remaining > 0) {
    for (let index = 0; index < parts.length; index += 1) {
      if (cursors[index] < parts[index].length) {
        woven.push(parts[index][cursors[index]]);
        cursors[index] += 1;
        remaining -= 1;
      }
    }
  }
  return woven;
}
