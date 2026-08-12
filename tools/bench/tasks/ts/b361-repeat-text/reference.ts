export function repeatText(
  phrase: string,
  times: number,
  between: string,
): string {
  if (times <= 0) {
    return "";
  }
  const copies: string[] = [];
  for (let i = 0; i < times; i += 1) {
    copies.push(phrase);
  }
  return copies.join(between);
}
