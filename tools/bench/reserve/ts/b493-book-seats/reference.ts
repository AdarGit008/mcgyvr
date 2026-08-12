export function seatRow(seat: string): string {
  return seat.slice(0, 1);
}

/** Seat codes gathered under their row, in arriving order. */
export function bookSeats(seats: string[]): Record<string, string[]> {
  const rows: Record<string, string[]> = {};
  const taken: string[] = [];
  for (const seat of seats) {
    if (taken.includes(seat)) {
      throw new Error("the seat " + seat + " is already booked");
    }
    taken.push(seat);
    const row = seatRow(seat);
    if (!(row in rows)) {
      rows[row] = [];
    }
    rows[row].push(seat);
  }
  return rows;
}
