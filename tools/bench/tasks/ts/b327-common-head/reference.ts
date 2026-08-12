export function commonHead(words: string[]): string {
  if (words.length === 0) {
    return "";
  }
  let head = words[0];
  for (const word of words.slice(1)) {
    while (!word.startsWith(head)) {
      head = head.slice(0, -1);
    }
  }
  return head;
}
