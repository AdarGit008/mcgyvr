/** Render a value as fixed-width unsigned binary, nibble-grouped. */
export function formatBits(value: number, width: number): string {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error("value must be a non-negative integer");
  }
  if (!Number.isInteger(width) || width <= 0 || width % 4 !== 0 || width > 32) {
    throw new Error("width must be a positive multiple of 4, at most 32");
  }
  if (value >= 2 ** width) {
    throw new Error("value does not fit in the width");
  }
  const groups: string[] = [];
  for (let start = width - 4; start >= 0; start -= 4) {
    let nibble = "";
    for (let bit = start + 3; bit >= start; bit--) {
      nibble += (value >>> bit) & 1 ? "1" : "0";
    }
    groups.push(nibble);
  }
  return groups.join(" ");
}
