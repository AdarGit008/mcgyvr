export function shingleOverlapRatio(
  left: string,
  right: string,
  width: number,
): number[] {
  if (!Number.isInteger(width) || width <= 0) {
    throw new Error("width must be a positive whole number");
  }
  const windows = (passage: string): Set<string> => {
    if (typeof passage !== "string") {
      throw new Error("a passage must be a string");
    }
    const tokens = passage.split(" ").filter((token) => token.length > 0);
    if (tokens.length === 0) {
      throw new Error("a passage must carry at least one token");
    }
    if (tokens.length < width) {
      throw new Error("a passage carries fewer tokens than the width");
    }
    const held = new Set<string>();
    for (let start = 0; start + width <= tokens.length; start++) {
      held.add(tokens.slice(start, start + width).join(" "));
    }
    return held;
  };

  const here = windows(left);
  const there = windows(right);
  let shared = 0;
  for (const window of here) {
    if (there.has(window)) {
      shared += 1;
    }
  }
  if (shared === 0) {
    return [0, 1];
  }
  const either = here.size + there.size - shared;
  let a = shared;
  let b = either;
  while (b !== 0) {
    const carry = a % b;
    a = b;
    b = carry;
  }
  return [shared / a, either / a];
}
