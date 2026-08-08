function gcd(a: number, b: number): number {
  while (b !== 0) {
    [a, b] = [b, a % b];
  }
  return a < 0 ? -a : a;
}

export function combineFractions(parts: string[]): string {
  if (!Array.isArray(parts) || parts.length === 0) {
    throw new Error("combineFractions expects a non-empty list");
  }
  let num = 0;
  let den = 1;
  for (const part of parts) {
    if (typeof part !== "string" || !/^-?\d+\/\d+$/.test(part)) {
      throw new Error(`malformed fraction: ${String(part)}`);
    }
    const [a, b] = part.split("/");
    const n = Number(a);
    const d = Number(b);
    if (d === 0) {
      throw new Error(`zero denominator: ${part}`);
    }
    num = num * d + n * den;
    den = den * d;
    const g = gcd(num, den);
    if (g > 1) {
      num /= g;
      den /= g;
    }
  }
  if (num === 0) {
    return "0/1";
  }
  return `${num}/${den}`;
}
