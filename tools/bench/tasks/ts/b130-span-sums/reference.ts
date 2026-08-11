/** Tape-measure spans: parse to inches, format canonically, and add. */

const INCHES: Record<string, number> = { yd: 36, ft: 12, in: 1 };
const ORDER = ["yd", "ft", "in"];

export function parseSpan(text: string): number {
  if (typeof text !== "string") {
    throw new Error("a span must be a string");
  }
  if (text === "") {
    throw new Error("a span must not be empty");
  }
  let total = 0;
  let rank = -1;
  for (const part of text.split(" ")) {
    const match = /^(0|[1-9]\d*)([a-z]+)$/.exec(part);
    if (match === null) {
      throw new Error(`malformed span part: ${part}`);
    }
    const unit = match[2];
    const at = ORDER.indexOf(unit);
    if (at < 0) {
      throw new Error(`unknown unit: ${unit}`);
    }
    if (at <= rank) {
      throw new Error(`units out of order or repeated: ${part}`);
    }
    rank = at;
    total += Number(match[1]) * INCHES[unit];
  }
  return total;
}

export function formatSpan(inches: number): string {
  if (!Number.isInteger(inches) || inches < 0) {
    throw new Error("inches must be a non-negative integer");
  }
  if (inches === 0) {
    return "0in";
  }
  const parts: string[] = [];
  const yards = Math.floor(inches / 36);
  const feet = Math.floor((inches % 36) / 12);
  const rest = inches % 12;
  if (yards > 0) {
    parts.push(`${yards}yd`);
  }
  if (feet > 0) {
    parts.push(`${feet}ft`);
  }
  if (rest > 0) {
    parts.push(`${rest}in`);
  }
  return parts.join(" ");
}

export function addSpans(first: string, second: string): string {
  const total = parseSpan(first) + parseSpan(second);
  return formatSpan(total);
}
