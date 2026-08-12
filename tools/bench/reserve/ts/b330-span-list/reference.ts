export function rangeText(first: number, last: number): string {
  if (first === last) {
    return String(first);
  }
  return String(first) + "-" + String(last);
}

export function spanList(numbers: number[]): string[] {
  const spans: string[] = [];
  let start = 0;
  for (let i = 1; i <= numbers.length; i += 1) {
    if (i === numbers.length || numbers[i] !== numbers[i - 1] + 1) {
      spans.push(rangeText(numbers[start], numbers[i - 1]));
      start = i;
    }
  }
  return spans;
}
