export function stackPop(orders: string[]): string[] {
  const pile: string[] = [];
  for (const order of orders) {
    if (order === "take") {
      if (pile.length === 0) {
        throw new Error("there is nothing left to take");
      }
      pile.pop();
    } else {
      pile.push(order);
    }
  }
  return pile;
}
