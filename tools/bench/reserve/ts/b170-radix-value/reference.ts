export function radixValue(literal: string): number {
  if (typeof literal !== "string") {
    throw new Error("radixValue expects a string");
  }
  const mark = literal.indexOf("#");
  if (mark < 0) throw new Error("literal needs a hash mark");
  const base = Number(literal.slice(0, mark));
  if (!/^\d+$/.test(literal.slice(0, mark)) || base < 2 || base > 16) {
    throw new Error("base must be a decimal number from 2 to 16");
  }
  const digits = literal.slice(mark + 1);
  if (digits === "") throw new Error("digit part is empty");
  let value = 0;
  for (const ch of digits) {
    const worth = "0123456789abcdef".indexOf(ch);
    if (worth < 0 || worth >= base) throw new Error("a digit must be valued under the base");
    value = value * base + worth;
  }
  return value;
}
