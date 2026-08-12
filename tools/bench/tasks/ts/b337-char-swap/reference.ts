export function swapPair(first: string, second: string): string {
  return second + first;
}

export function swapAll(text: string): string {
  let out = "";
  for (let i = 0; i + 1 < text.length; i += 2) {
    out += swapPair(text[i], text[i + 1]);
  }
  if (text.length % 2 === 1) {
    out += text[text.length - 1];
  }
  return out;
}
