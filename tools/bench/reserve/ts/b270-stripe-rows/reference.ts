export function stripeRows(rows: number, colours: string[]): string[] {
  const painted: string[] = [];
  for (let i = 0; i < rows; i += 1) {
    painted.push(colours[i % colours.length]);
  }
  return painted;
}
