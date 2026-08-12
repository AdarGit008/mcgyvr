export function turnText(first: string, second: string): boolean {
  if (first.length !== second.length) {
    return false;
  }
  if (first.length === 0) {
    return true;
  }
  return (first + first).includes(second);
}
