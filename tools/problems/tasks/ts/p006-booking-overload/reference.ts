export function firstOverload(bookings: number[][], capacity: number): number {
  if (typeof capacity !== "number" || !Number.isInteger(capacity) || capacity < 1) {
    throw new Error("capacity must be a positive integer");
  }
  if (!Array.isArray(bookings)) {
    throw new Error("bookings must be a list of pairs");
  }
  const events: [number, number][] = [];
  for (const booking of bookings) {
    if (!Array.isArray(booking) || booking.length !== 2) {
      throw new Error("each booking is a pair of endpoints");
    }
    const [start, end] = booking;
    if (!Number.isInteger(start) || !Number.isInteger(end)) {
      throw new Error("booking endpoints must be integers");
    }
    if (start >= end) {
      throw new Error("booking start must come strictly before its end");
    }
    events.push([start, 1]);
    events.push([end, -1]);
  }
  events.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let active = 0;
  for (const [time, delta] of events) {
    active += delta;
    if (active > capacity) {
      return time;
    }
  }
  return -1;
}
