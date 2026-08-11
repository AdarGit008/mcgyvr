export function hopChain(hops: string[][]): boolean {
  for (let i = 1; i < hops.length; i += 1) {
    if (hops[i - 1][1] !== hops[i][0]) {
      return false;
    }
  }
  return true;
}
