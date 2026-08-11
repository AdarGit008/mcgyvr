export function repeatWords(text: string, least: number): string[] {
  if (typeof text !== "string") {
    throw new Error("repeatWords expects a string");
  }
  if (!Number.isInteger(least) || least < 1) {
    throw new Error("least must be a positive whole number");
  }
  if (!/^[A-Za-z ]*$/.test(text)) {
    throw new Error("text may hold only ASCII letters and spaces");
  }
  const counts = new Map<string, number>();
  for (const word of text.split(" ")) {
    if (word === "") continue;
    const folded = word.toLowerCase();
    counts.set(folded, (counts.get(folded) ?? 0) + 1);
  }
  return [...counts].filter(([, seen]) => seen >= least).map(([word]) => word);
}
