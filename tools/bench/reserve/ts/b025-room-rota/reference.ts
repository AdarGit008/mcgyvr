/** A small room rota: overlap test, room assignment, and peak occupancy. */

function checkSpan(span: number[], label: string): void {
  const [start, end] = span;
  if (!Number.isInteger(start) || !Number.isInteger(end)) {
    throw new Error(`${label} endpoints must be integers`);
  }
  if (start >= end) {
    throw new Error(`${label} start must precede its end`);
  }
}

export function spansOverlap(a: number[], b: number[]): boolean {
  checkSpan(a, "span");
  checkSpan(b, "span");
  return a[0] < b[1] && b[0] < a[1];
}

export function assignRooms(meetings: number[][]): number[] {
  for (const meeting of meetings) {
    checkSpan(meeting, "meeting");
  }
  const order = meetings
    .map((meeting, position) => ({ meeting, position }))
    .sort(
      (left, right) =>
        left.meeting[0] - right.meeting[0] ||
        left.meeting[1] - right.meeting[1] ||
        left.position - right.position,
    );
  // One entry per open room: the meeting currently holding it. Seating in
  // chronological order keeps the returned indices aligned with the input.
  const lastInRoom: number[][] = [];
  const rooms: number[] = new Array(meetings.length).fill(0);
  for (const { meeting, position } of order) {
    let assigned = -1;
    for (let room = 0; room < lastInRoom.length; room++) {
      if (!spansOverlap(lastInRoom[room], meeting)) {
        assigned = room;
        break;
      }
    }
    if (assigned === -1) {
      assigned = lastInRoom.length;
      lastInRoom.push(meeting);
    } else {
      lastInRoom[assigned] = meeting;
    }
    rooms[position] = assigned;
  }
  return rooms;
}

export function peakRooms(meetings: number[][]): number {
  const rooms = assignRooms(meetings);
  let peak = 0;
  for (const room of rooms) {
    peak = Math.max(peak, room + 1);
  }
  return peak;
}
