export function pairOff(marks: string[]): string[] {
  const left: string[] = [];
  for (const mark of marks) {
    if (left.length > 0 && left[left.length - 1] === mark) {
      left.pop();
    } else {
      left.push(mark);
    }
  }
  return left;
}
