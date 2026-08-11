export function normalizeSeats(raw: string[]): string[] {
  if (!Array.isArray(raw)) {
    throw new Error("normalizeSeats expects a list");
  }
  const seats: string[] = [];
  const seen = new Set<string>();
  for (const entry of raw) {
    if (typeof entry !== "string") {
      throw new Error("seat entries must be strings");
    }
    if (entry.trim() === "") {
      throw new Error("blank seat entry");
    }
    const match = entry.match(/^\s*([A-Za-z])-?(\d{1,3})\s*$/);
    if (match === null) {
      throw new Error("malformed seat: " + entry);
    }
    const number = Number(match[2]);
    if (number === 0) {
      throw new Error("seat numbers start at 1");
    }
    const seat = match[1].toUpperCase() + number;
    if (seen.has(seat)) {
      throw new Error("duplicate seat: " + seat);
    }
    seen.add(seat);
    seats.push(seat);
  }
  return seats;
}
