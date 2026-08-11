export function weighIn(grams: number): number[] {
  if (grams < 0) {
    throw new Error("weight cannot be negative");
  }
  const kilos = Math.floor(grams / 1000);
  return [kilos, grams - kilos * 1000];
}
