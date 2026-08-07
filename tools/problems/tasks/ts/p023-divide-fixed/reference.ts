export function divideFixed(
  numerator: number,
  denominator: number,
  places: number,
): string {
  if (
    !Number.isInteger(numerator) ||
    !Number.isInteger(denominator) ||
    !Number.isInteger(places)
  ) {
    throw new Error("divideFixed expects integer arguments");
  }
  if (denominator === 0) {
    throw new Error("division by zero");
  }
  if (places < 0 || places > 6) {
    throw new Error("places must be within 0..6");
  }
  const negative = numerator < 0 !== denominator < 0;
  const n = Math.abs(numerator);
  const d = Math.abs(denominator);
  const scaled = n * 10 ** places;
  let q = Math.floor(scaled / d);
  const r = scaled % d;
  if (2 * r > d || (2 * r === d && q % 2 === 1)) {
    q += 1;
  }
  const digits = String(q).padStart(places + 1, "0");
  const whole = digits.slice(0, digits.length - places);
  const frac = places > 0 ? "." + digits.slice(digits.length - places) : "";
  const sign = negative && q !== 0 ? "-" : "";
  return sign + whole + frac;
}
