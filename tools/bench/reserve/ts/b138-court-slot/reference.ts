/** Insert a requested slot into a court's booking sheet for the day. */

export function reserveCourt(
  booked: number[][],
  slot: number[],
  hours: number[],
): number[][] {
  for (const pair of [hours, slot]) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("hours and slot must be two-item lists");
    }
    if (!Number.isInteger(pair[0]) || !Number.isInteger(pair[1])) {
      throw new Error("bounds must be whole minutes");
    }
  }
  const [openAt, closeAt] = hours;
  if (openAt >= closeAt) {
    throw new Error("opening must precede closing");
  }
  const [from, until] = slot;
  if (from >= until) {
    throw new Error("slot start must precede its end");
  }
  if (from < openAt || until > closeAt) {
    throw new Error("slot must lie inside opening hours");
  }
  if (!Array.isArray(booked)) {
    throw new Error("booked must be a list");
  }
  const sheet: number[][] = [];
  for (const entry of booked) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("each booking must be a two-item list");
    }
    if (!Number.isInteger(entry[0]) || !Number.isInteger(entry[1])) {
      throw new Error("booking bounds must be whole minutes");
    }
    if (entry[0] >= entry[1]) {
      throw new Error("booking start must precede its end");
    }
    sheet.push([entry[0], entry[1]]);
  }
  sheet.sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < sheet.length; i++) {
    if (sheet[i - 1][1] > sheet[i][0]) {
      throw new Error("existing bookings overlap one another");
    }
  }
  for (const [start, end] of sheet) {
    if (from < end && start < until) {
      throw new Error("slot overlaps an existing booking");
    }
  }
  let at = sheet.length;
  for (let i = 0; i < sheet.length; i++) {
    if (until <= sheet[i][0]) {
      at = i;
      break;
    }
  }
  sheet.splice(at, 0, [from, until]);
  return sheet;
}
