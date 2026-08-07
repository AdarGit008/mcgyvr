type Need = { item: string; per: number };
type Recipe = { item: string; needs: Need[] };
type Held = { item: string; held: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function netRequirements(
  recipes: Recipe[],
  stock: Held[],
  target: string,
  batch: number,
): { item: string; buy: number }[] {
  if (!Array.isArray(recipes)) {
    throw new Error("recipes must be a list");
  }
  if (!Array.isArray(stock)) {
    throw new Error("stock must be a list");
  }
  if (typeof target !== "string" || target.length === 0) {
    throw new Error("target must be a non-empty string");
  }
  if (!whole(batch) || batch < 1) {
    throw new Error("batch must be an integer of at least 1");
  }

  const index = new Map<string, Need[]>();
  for (const recipe of recipes) {
    if (recipe === null || typeof recipe !== "object") {
      throw new Error("a recipes entry must be a record");
    }
    if (typeof recipe.item !== "string" || recipe.item.length === 0) {
      throw new Error("an item name must be a non-empty string");
    }
    if (index.has(recipe.item)) {
      throw new Error("recipes gives the same item twice: " + recipe.item);
    }
    if (!Array.isArray(recipe.needs) || recipe.needs.length === 0) {
      throw new Error("needs must be a non-empty list: " + recipe.item);
    }
    const here = new Set<string>();
    for (const need of recipe.needs) {
      if (need === null || typeof need !== "object") {
        throw new Error("a needs entry must be a record");
      }
      if (typeof need.item !== "string" || need.item.length === 0) {
        throw new Error("an item name must be a non-empty string");
      }
      if (here.has(need.item)) {
        throw new Error(recipe.item + " names " + need.item + " twice");
      }
      here.add(need.item);
      if (!whole(need.per) || need.per < 1) {
        throw new Error("per must be an integer of at least 1: " + need.item);
      }
    }
    index.set(recipe.item, recipe.needs);
  }

  const remaining = new Map<string, number>();
  for (const shelf of stock) {
    if (shelf === null || typeof shelf !== "object") {
      throw new Error("a stock entry must be a record");
    }
    if (typeof shelf.item !== "string" || shelf.item.length === 0) {
      throw new Error("an item name must be a non-empty string");
    }
    if (remaining.has(shelf.item)) {
      throw new Error("stock gives the same item twice: " + shelf.item);
    }
    if (!whole(shelf.held) || shelf.held < 0) {
      throw new Error("held must be an integer of at least 0: " + shelf.item);
    }
    remaining.set(shelf.item, shelf.held);
  }

  const buy = new Map<string, number>();
  const chain = new Set<string>();

  const make = (item: string, units: number): void => {
    if (chain.has(item)) {
      throw new Error("the making loops through " + item);
    }
    chain.add(item);
    for (const need of index.get(item) as Need[]) {
      const call = units * need.per;
      const have = remaining.get(need.item) ?? 0;
      const drawn = have < call ? have : call;
      remaining.set(need.item, have - drawn);
      const standing = call - drawn;
      if (standing === 0) {
        continue;
      }
      if (index.has(need.item)) {
        make(need.item, standing);
      } else {
        buy.set(need.item, (buy.get(need.item) ?? 0) + standing);
      }
    }
    chain.delete(item);
  };

  if (index.has(target)) {
    make(target, batch);
  } else {
    buy.set(target, batch);
  }

  const names = [...buy.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  return names.map((item) => ({ item, buy: buy.get(item) as number }));
}
