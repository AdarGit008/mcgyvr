type Called = { name: string; band: number; klass: number; row: number; place: number };

function isCount(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

export function orderBoardingBands(
  layout: string,
  rows: number,
  band: number,
  passengers: Array<[string, string]>,
): string[] {
  if (typeof layout !== "string") {
    throw new Error("the layout is a string");
  }
  const sides = layout.split("|");
  if (sides.length !== 2) {
    throw new Error("the layout carries exactly one aisle bar");
  }
  if (sides[0].length === 0 || sides[1].length === 0) {
    throw new Error("both sides of the aisle carry seats");
  }
  const letters = sides[0] + sides[1];
  const place = new Map<string, number>();
  for (let i = 0; i < letters.length; i++) {
    const letter = letters[i];
    if (letter < "A" || letter > "Z") {
      throw new Error("a seat letter is a capital letter");
    }
    if (place.has(letter)) {
      throw new Error("the layout writes " + letter + " twice");
    }
    place.set(letter, i);
  }
  if (!isCount(rows) || !isCount(band)) {
    throw new Error("rows and the band size are whole numbers of one or more");
  }
  if (!Array.isArray(passengers)) {
    throw new Error("the passenger list is a list");
  }

  const windows = new Set<string>([sides[0][0], sides[1][sides[1].length - 1]]);
  const aisles = new Set<string>([sides[0][sides[0].length - 1], sides[1][0]]);
  const names = new Set<string>();
  const seats = new Set<string>();
  const called: Called[] = [];
  for (const entry of passengers) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("a passenger is a pair of a name and a seat");
    }
    const name = entry[0];
    const seat = entry[1];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name is a non-empty string");
    }
    if (names.has(name)) {
      throw new Error("two passengers answer to " + name);
    }
    names.add(name);
    if (typeof seat !== "string") {
      throw new Error("a seat is a string");
    }
    const parsed = /^(\d+)([A-Z])$/.exec(seat);
    if (parsed === null) {
      throw new Error("a seat is digits followed by one letter");
    }
    const row = Number(parsed[1]);
    const letter = parsed[2];
    if (row < 1 || row > rows) {
      throw new Error("row " + String(row) + " is not in this cabin");
    }
    if (!place.has(letter)) {
      throw new Error("the layout has no seat " + letter);
    }
    const key = String(row) + letter;
    if (seats.has(key)) {
      throw new Error("two passengers hold seat " + key);
    }
    seats.add(key);
    const klass = windows.has(letter) ? 0 : aisles.has(letter) ? 2 : 1;
    called.push({
      name,
      band: Math.floor((rows - row) / band) + 1,
      klass,
      row,
      place: place.get(letter),
    });
  }

  called.sort((a, b) => {
    if (a.band !== b.band) return a.band - b.band;
    if (a.klass !== b.klass) return a.klass - b.klass;
    if (a.row !== b.row) return b.row - a.row;
    return a.place - b.place;
  });
  return called.map((one) => one.name);
}
