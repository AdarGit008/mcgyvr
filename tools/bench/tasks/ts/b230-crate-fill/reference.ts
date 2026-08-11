export function crateFill(items: number, crates: number): number[] {
  const sizes: number[] = [];
  for (let i = 0; i < crates; i += 1) {
    sizes.push(Math.floor(items / crates) + (i < items % crates ? 1 : 0));
  }
  return sizes;
}

export function crateTotal(sizes: number[]): number {
  return sizes.reduce((sum, size) => sum + size, 0);
}
