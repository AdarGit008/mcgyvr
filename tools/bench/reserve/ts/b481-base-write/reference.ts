export function baseWrite(value: number, base: number): string {
  if (base < 2 || base > 16) {
    throw new Error("the base must stand between two and sixteen");
  }
  const figures = "0123456789abcdef";
  if (value === 0) {
    return "0";
  }
  let left = value;
  let out = "";
  while (left > 0) {
    out = figures[left % base] + out;
    left = Math.floor(left / base);
  }
  return out;
}
