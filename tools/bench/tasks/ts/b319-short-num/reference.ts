export function shortNum(value: number): string {
  const sizes: [number, string][] = [
    [1000000, "m"],
    [1000, "k"],
  ];
  for (const [size, suffix] of sizes) {
    if (value >= size) {
      const tenths = Math.floor((value * 10) / size);
      return String(Math.floor(tenths / 10)) + "." + String(tenths % 10) + suffix;
    }
  }
  return String(value);
}
