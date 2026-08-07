export function shiftFrontCodes(alphabet: string, message: string): number[] {
  if (typeof alphabet !== "string") {
    throw new Error("the alphabet must be a string");
  }
  if (alphabet.length === 0) {
    throw new Error("the alphabet must not be empty");
  }
  const row = Array.from(alphabet);
  if (new Set(row).size !== row.length) {
    throw new Error("the alphabet carries a character twice over");
  }
  if (typeof message !== "string") {
    throw new Error("the message must be a string");
  }
  const places: number[] = [];
  for (const character of Array.from(message)) {
    const place = row.indexOf(character);
    if (place < 0) {
      throw new Error("the message holds a character the alphabet lacks");
    }
    places.push(place);
    row.splice(place, 1);
    row.unshift(character);
  }
  return places;
}
