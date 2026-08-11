export function unitMix(
  units: number,
  parts: number,
  perUnit: number,
): number[] {
  if (perUnit <= 0) {
    throw new Error("a unit must hold parts");
  }
  const carried = Math.floor(parts / perUnit);
  return [units + carried, parts - carried * perUnit];
}
