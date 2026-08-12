export function clipText(text: string, from: number, to: number): string {
  if (from > to) {
    throw new Error("the first place must not stand above the second");
  }
  const start = from > text.length ? text.length : from;
  const stop = to > text.length ? text.length : to;
  return text.slice(start, stop);
}
