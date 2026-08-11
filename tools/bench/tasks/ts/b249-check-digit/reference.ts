export function checkDigit(code: string): number {
  let sum = 0;
  for (const ch of code) {
    if (ch < "0" || ch > "9") {
      throw new Error("not a digit: " + ch);
    }
    sum += Number(ch);
  }
  return (10 - (sum % 10)) % 10;
}
