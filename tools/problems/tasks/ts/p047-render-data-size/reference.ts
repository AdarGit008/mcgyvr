export function renderDataSize(total: number): string {
  if (typeof total !== "number" || !Number.isInteger(total) || total < 0) {
    throw new Error("count must be a non-negative integer");
  }
  const ladder: [string, number][] = [
    ["GiB", 1024 * 1024 * 1024],
    ["MiB", 1024 * 1024],
    ["KiB", 1024],
    ["B", 1],
  ];
  const parts: string[] = [];
  let rest = total;
  for (const [suffix, size] of ladder) {
    const count = Math.floor(rest / size);
    if (count > 0) {
      parts.push(`${count}${suffix}`);
    }
    rest -= count * size;
  }
  return parts.length === 0 ? "0B" : parts.join(" ");
}
