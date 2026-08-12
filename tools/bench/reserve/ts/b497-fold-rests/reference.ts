export function isRest(entry: string): boolean {
  return entry.trim().length === 0;
}

/** The run with each unbroken stretch of rests standing as one dash. */
export function foldRests(entries: string[]): string[] {
  const out: string[] = [];
  let resting = false;
  for (const entry of entries) {
    if (isRest(entry)) {
      if (!resting) {
        out.push("-");
        resting = true;
      }
    } else {
      out.push(entry);
      resting = false;
    }
  }
  return out;
}
