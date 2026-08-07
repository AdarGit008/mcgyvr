export function denseRankMap(values: number[], order: string): number[] {
  if (order !== "asc" && order !== "desc") {
    throw new Error("bad order word");
  }
  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("empty value list");
  }
  for (const v of values) {
    if (typeof v !== "number" || !Number.isInteger(v)) {
      throw new Error("non-integer value");
    }
  }
  const distinct = [...new Set(values)].sort((a, b) =>
    order === "asc" ? a - b : b - a,
  );
  const rankOf = new Map<number, number>();
  distinct.forEach((v, i) => rankOf.set(v, i + 1));
  return values.map((v) => rankOf.get(v) as number);
}
