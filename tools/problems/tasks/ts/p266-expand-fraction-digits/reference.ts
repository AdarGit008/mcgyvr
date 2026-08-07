const GLYPHS = "0123456789ABCDEFGHIJ";

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function expandFractionDigits(
  numerator: number,
  denominator: number,
  base: number
): string {
  if (!whole(numerator) || !whole(denominator) || !whole(base)) {
    throw new Error("all three arguments must be whole numbers");
  }
  if (base < 3 || base > 20) {
    throw new Error("base must lie in 3..20");
  }
  if (denominator < 1) {
    throw new Error("denominator must be a positive whole number");
  }
  if (Math.abs(numerator) > 1000000 || denominator > 1000000) {
    throw new Error("magnitudes must stay at or below one million");
  }

  const negative = numerator < 0;
  const magnitude = Math.abs(numerator);
  let head = Math.floor(magnitude / denominator);
  const rest = magnitude % denominator;

  let stem = "";
  if (head === 0) {
    stem = "0";
  } else {
    while (head > 0) {
      stem = GLYPHS[head % base] + stem;
      head = Math.floor(head / base);
    }
  }
  if (rest === 0) {
    return (negative ? "-" : "") + stem;
  }

  const seen = new Map();
  const tail: string[] = [];
  let carry = rest;
  let repeat = -1;
  while (carry !== 0) {
    if (seen.has(carry)) {
      repeat = seen.get(carry);
      break;
    }
    seen.set(carry, tail.length);
    const scaled = carry * base;
    tail.push(GLYPHS[Math.floor(scaled / denominator)]);
    carry = scaled % denominator;
  }

  const body =
    repeat === -1
      ? tail.join("")
      : tail.slice(0, repeat).join("") + "[" + tail.slice(repeat).join("") + "]";
  return (negative ? "-" : "") + stem + ";" + body;
}
