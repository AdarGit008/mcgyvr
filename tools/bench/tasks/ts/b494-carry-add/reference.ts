export function carryAdd(left: number[], right: number[]): number[] {
  const out: number[] = [];
  let carried = 0;
  let i = left.length - 1;
  let j = right.length - 1;
  while (i >= 0 || j >= 0 || carried > 0) {
    const a = i >= 0 ? left[i] : 0;
    const b = j >= 0 ? right[j] : 0;
    const total = a + b + carried;
    out.unshift(total % 10);
    carried = total >= 10 ? 1 : 0;
    i -= 1;
    j -= 1;
  }
  return out;
}
