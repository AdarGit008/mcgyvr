/** Total the base parts an order of a kit consumes. */
export function explodeKit(catalog: Record<string, { makes: number; parts: [string, number][] }>, kit: string, want: number): Record<string, number> {
  if (!Object.prototype.hasOwnProperty.call(catalog, kit)) {
    throw new Error(`the catalog does not define ${kit}`);
  }
  const totals: Record<string, number> = {};
  const order = (name: string, units: number): void => {
    const recipe = catalog[name];
    const runs = Math.ceil(units / recipe.makes);
    for (const [component, count] of recipe.parts) {
      const needed = runs * count;
      if (Object.prototype.hasOwnProperty.call(catalog, component)) {
        order(component, needed);
      } else {
        totals[component] = (totals[component] ?? 0) + needed;
      }
    }
  };
  order(kit, want);
  return totals;
}
