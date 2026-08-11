export function shareOut(amount: number, parts: number): number[] {
  if (parts < 1) {
    throw new Error("there must be at least one part");
  }
  const base = Math.floor(amount / parts);
  const over = amount % parts;
  const out: number[] = [];
  for (let i = 0; i < parts; i += 1) {
    if (i < over) {
      out.push(base + 1);
    } else {
      out.push(base);
    }
  }
  return out;
}
