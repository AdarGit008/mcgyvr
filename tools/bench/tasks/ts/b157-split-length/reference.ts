const LADDER: [string, number][] = [["m", 1000], ["cm", 10], ["mm", 1]];

export function splitLength(mm: number): string {
  if (typeof mm !== "number" || !Number.isInteger(mm)) throw new Error("length must be a whole number of millimetres");
  if (mm < 0) throw new Error("length must not be negative");
  const parts: string[] = [];
  let rest = mm;
  for (const [unit, size] of LADDER) {
    const count = Math.floor(rest / size);
    rest %= size;
    if (count > 0) parts.push(`${count}${unit}`);
  }
  return parts.length > 0 ? parts.join(" ") : "0mm";
}
