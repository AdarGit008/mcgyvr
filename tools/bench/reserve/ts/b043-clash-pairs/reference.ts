/** Which appointment bookings collide with one another. */
export function clashPairs(bookings: number[][]): number[][] {
  if (!Array.isArray(bookings)) {
    throw new Error("clashPairs expects a list of bookings");
  }
  for (const booking of bookings) {
    if (!Array.isArray(booking) || booking.length !== 2) {
      throw new Error("a booking must be a [start, end] pair");
    }
    const [start, end] = booking;
    if (!Number.isInteger(start) || !Number.isInteger(end)) {
      throw new Error("booking bounds must be integers");
    }
    if (start >= end) {
      throw new Error("booking start must precede its end");
    }
  }
  const pairs: number[][] = [];
  for (let i = 0; i < bookings.length; i++) {
    for (let j = i + 1; j < bookings.length; j++) {
      if (bookings[i][0] < bookings[j][1] && bookings[j][0] < bookings[i][1]) {
        pairs.push([i, j]);
      }
    }
  }
  return pairs;
}
