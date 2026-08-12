export function hugText(text: string, mark: string): string {
  if (
    text.startsWith(mark) &&
    text.endsWith(mark) &&
    text.length >= mark.length * 2
  ) {
    return text;
  }
  return mark + text + mark;
}
