export function lineCost(price: number, quantity: number): number {
  return price * quantity;
}

export function basketCost(
  lines: { price: number; quantity: number }[],
  discount: number,
): number {
  let total = 0;
  for (const line of lines) {
    total += lineCost(line.price, line.quantity);
  }
  return Math.floor((total * (100 - discount)) / 100);
}
