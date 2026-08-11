/** Reduce a hexadecimal colour to a packed bit word rendered in binary. */
export function swatchWord(hex: string, depths: number[]): string {
  if (typeof hex !== "string" || !/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(hex)) {
    throw new Error("colour must be #rgb or #rrggbb");
  }
  if (depths.length !== 3 || depths.some((d) => !Number.isInteger(d) || d < 1 || d > 8)) {
    throw new Error("depths must be three widths from 1 to 8");
  }
  let digits = hex.slice(1);
  if (digits.length === 3) {
    digits = digits[0] + digits[0] + digits[1] + digits[1] + digits[2] + digits[2];
  }
  let word = 0;
  let total = 0;
  for (let index = 0; index < 3; index++) {
    const channel = parseInt(digits.slice(index * 2, index * 2 + 2), 16);
    const depth = depths[index];
    word = (word << depth) | (channel >> (8 - depth));
    total += depth;
  }
  return word.toString(2).padStart(total, "0");
}
