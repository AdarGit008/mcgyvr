export function normalizePartCode(code: string): string {
  if (typeof code !== "string") {
    throw new Error("normalizePartCode expects a string");
  }
  let cleaned = "";
  for (const ch of code) {
    if (ch === " " || ch === "-") {
      continue;
    }
    const upper = ch.toUpperCase();
    if (!/^[0-9A-Z]$/.test(upper)) {
      throw new Error(`invalid character ${ch}`);
    }
    cleaned += upper;
  }
  if (cleaned.length !== 9) {
    throw new Error("expected nine characters after cleaning");
  }
  const value = (ch: string): number => Number.parseInt(ch, 36);
  const weights = [3, 5, 7, 3, 5, 7, 3, 5];
  let sum = 0;
  for (let i = 0; i < 8; i++) {
    sum += value(cleaned[i]) * weights[i];
  }
  if (value(cleaned[8]) !== sum % 36) {
    throw new Error("check character does not verify");
  }
  return `${cleaned.slice(0, 4)}-${cleaned.slice(4, 8)}-${cleaned[8]}`;
}
