export function clipLabel(label: string, budget: number): string {
  if (typeof label !== "string") {
    throw new Error("label must be a string");
  }
  if (typeof budget !== "number" || !Number.isInteger(budget) || budget < 4) {
    throw new Error("budget must be an integer of at least 4");
  }
  if (label.length <= budget) {
    return label;
  }
  const kept = label.slice(0, budget - 3).replace(/ +$/, "");
  return kept + "...";
}
