export function menuPick(
  dishes: { name: string; price: number }[],
  budget: number,
): string[] {
  const affordable = dishes.filter((dish) => dish.price <= budget);
  affordable.sort((a, b) =>
    a.price === b.price ? a.name.localeCompare(b.name) : a.price - b.price,
  );
  return affordable.map((dish) => dish.name);
}
