export function padSide(count: number): string {
  if (count <= 0) {
    return "";
  }
  return " ".repeat(count);
}

export function padMid(word: string, width: number): string {
  const spare = width - word.length;
  const left = Math.floor(spare / 2);
  return padSide(left) + word + padSide(spare - left);
}
