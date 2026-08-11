export function fuelLegs(litres: number, burn: number): number {
  if (burn <= 0) {
    throw new Error("burn must be positive");
  }
  let left = litres;
  let legs = 0;
  while (left >= burn) {
    left -= burn;
    legs += 1;
  }
  return legs;
}
