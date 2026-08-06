/** Schoolbook addition of decimal strings, right to left with a carry. */
export function addDecimalStrings(a: string, b: string): string {
  for (const operand of [a, b]) {
    if (typeof operand !== "string" || !/^[0-9]+$/.test(operand)) {
      throw new Error("each argument must be a non-empty string of digits 0-9");
    }
  }
  const digits: number[] = [];
  let i = a.length - 1;
  let j = b.length - 1;
  let carry = 0;
  while (i >= 0 || j >= 0 || carry > 0) {
    const da = i >= 0 ? a.charCodeAt(i) - 48 : 0;
    const db = j >= 0 ? b.charCodeAt(j) - 48 : 0;
    const sum = da + db + carry;
    digits.push(sum % 10);
    carry = sum >= 10 ? 1 : 0;
    i -= 1;
    j -= 1;
  }
  const result = digits.reverse().join("");
  const trimmed = result.replace(/^0+(?=.)/, "");
  return trimmed;
}
