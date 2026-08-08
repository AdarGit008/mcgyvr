type Category = { label: string; weight: number; items: number[][] };

export function courseWeightTotal(
  categories: Array<Record<string, unknown>>
): number {
  if (!Array.isArray(categories) || categories.length === 0) {
    throw new Error("the syllabus holds no categories");
  }
  const labels = new Set<string>();
  let weights = 0;
  let answer = 0;
  for (const raw of categories) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a category must be a mapping");
    }
    const category = raw as unknown as Category;
    const label = category.label;
    if (typeof label !== "string" || label.length === 0) {
      throw new Error("a category needs a non-empty label");
    }
    if (labels.has(label)) {
      throw new Error("duplicate category label: " + label);
    }
    labels.add(label);
    const weight = category.weight;
    if (!Number.isInteger(weight) || weight < 0) {
      throw new Error("weight must be a non-negative whole number");
    }
    weights += weight;
    const items = category.items;
    if (!Array.isArray(items) || items.length === 0) {
      throw new Error("category " + label + " holds no items");
    }
    let earned = 0;
    let worth = 0;
    for (const item of items) {
      if (!Array.isArray(item) || item.length !== 2) {
        throw new Error("an item is a pair of whole numbers");
      }
      const [got, possible] = item;
      if (!Number.isInteger(got) || !Number.isInteger(possible)) {
        throw new Error("item points must be whole numbers");
      }
      if (possible <= 0) {
        throw new Error("an item must be worth something");
      }
      if (got < 0 || got > possible) {
        throw new Error("earned points fall outside the item's worth");
      }
      earned += got;
      worth += possible;
    }
    answer += Math.floor((weight * earned) / worth);
  }
  if (weights !== 10000) {
    throw new Error("weights add up to " + weights + ", not 10000");
  }
  return answer;
}
