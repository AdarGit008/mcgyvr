const DIGITS = "0123456789abcdef";

export function byteHex(value: number): string {
  return DIGITS[Math.floor(value / 16)] + DIGITS[value % 16];
}

export function bytesHex(values: number[]): string {
  let out = "";
  for (const value of values) {
    out += byteHex(value);
  }
  return out;
}
