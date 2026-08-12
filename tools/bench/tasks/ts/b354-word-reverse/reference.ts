export function wordReverse(line: string): string {
  const turned: string[] = [];
  for (const word of line.split(/\s+/)) {
    if (word !== "") {
      turned.push([...word].reverse().join(""));
    }
  }
  return turned.join(" ");
}
