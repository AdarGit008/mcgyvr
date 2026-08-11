export function overlapAny(bookings: number[][]): boolean {
  for (let i = 0; i < bookings.length; i += 1) {
    for (let j = i + 1; j < bookings.length; j += 1) {
      if (bookings[i][0] < bookings[j][1] && bookings[j][0] < bookings[i][1]) {
        return true;
      }
    }
  }
  return false;
}
