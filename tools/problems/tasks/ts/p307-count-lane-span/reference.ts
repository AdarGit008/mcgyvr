function place(label: string): number {
  if (label.length === 0 || label.length > 3 || !/^[A-Z]+$/.test(label)) {
    throw new Error("that is not a lane label");
  }
  let value = 0;
  for (const capital of label) {
    value = value * 26 + (capital.charCodeAt(0) - 64);
  }
  return value;
}

export function countLaneSpan(claims: string[]): number {
  if (!Array.isArray(claims) || claims.length === 0) {
    throw new Error("the batch must be a non-empty list");
  }
  const taken: number[][] = [];
  for (const claim of claims) {
    if (typeof claim !== "string") {
      throw new Error("a claim is a string");
    }
    const ends = claim.split(":");
    if (ends.length !== 2) {
      throw new Error("a claim holds exactly one colon");
    }
    const left = place(ends[0]);
    const right = place(ends[1]);
    if (left > right) {
      throw new Error("that claim runs backwards");
    }
    taken.push([left, right]);
  }
  taken.sort((a, b) => a[0] - b[0]);
  let counted = 0;
  let reached = 0;
  for (const [left, right] of taken) {
    const from = left > reached ? left : reached + 1;
    if (right >= from) {
      counted += right - from + 1;
    }
    if (right > reached) {
      reached = right;
    }
  }
  return counted;
}
