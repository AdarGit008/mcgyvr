/** Every second entry of a log, beginning with the first. */
export function everyOther(entries: string[]): string[] {
  return entries.filter((entry, index) => index % 2 === 0);
}
