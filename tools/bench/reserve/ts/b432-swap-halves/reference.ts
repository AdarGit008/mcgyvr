export function swapHalves(text: string): string {
  const cut = Math.ceil(text.length / 2);
  return text.slice(cut) + text.slice(0, cut);
}
