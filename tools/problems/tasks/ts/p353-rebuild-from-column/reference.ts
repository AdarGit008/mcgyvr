export function rebuildFromLastColumn(column: string, home: number): string {
  if (typeof column !== "string") {
    throw new Error("the column must be a string");
  }
  if (column.length === 0) {
    throw new Error("the column must not be empty");
  }
  if (!/^[a-z]+$/.test(column)) {
    throw new Error("the column holds a letter outside a to z");
  }
  if (typeof home !== "number" || !Number.isInteger(home)) {
    throw new Error("the home must be a whole number");
  }
  if (home < 0 || home >= column.length) {
    throw new Error("the home is outside the column");
  }
  const width = column.length;
  const seats: number[] = [];
  for (let place = 0; place < width; place++) {
    seats.push(place);
  }
  seats.sort((left, right) => {
    if (column[left] < column[right]) {
      return -1;
    }
    if (column[left] > column[right]) {
      return 1;
    }
    return left - right;
  });
  let seat = home;
  let text = "";
  for (let step = 0; step < width; step++) {
    seat = seats[seat];
    text += column[seat];
  }
  return text;
}
