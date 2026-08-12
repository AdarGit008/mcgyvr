export function hexSplit(colour: string): string[] {
  if (!/^#[0-9a-fA-F]{6}$/.test(colour)) {
    throw new Error("not a six-digit colour: " + colour);
  }
  return [colour.slice(1, 3), colour.slice(3, 5), colour.slice(5, 7)];
}

export function hexJoin(parts: string[]): string {
  return "#" + parts.join("").toLowerCase();
}
