export function fitBudget(prices: number[], budget: number): number {
  if (budget < 0) {
    throw new Error("budget cannot be negative");
  }
  let bought = 0;
  let left = budget;
  for (const price of [...prices].sort((a, b) => a - b)) {
    if (price > left) {
      break;
    }
    left -= price;
    bought += 1;
  }
  return bought;
}
