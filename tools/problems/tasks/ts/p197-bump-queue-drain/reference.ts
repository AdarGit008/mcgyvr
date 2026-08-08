/** The order a crew works through a batch of graded tickets. */

const CEILING = 9;

type Ticket = { id: string; filed: number; grade: number };

function urgency(ticket: Ticket, minute: number, bumpEvery: number): number {
  const bumps = Math.floor((minute - ticket.filed) / bumpEvery);
  const raw = ticket.grade + bumps;
  return raw > CEILING ? CEILING : raw;
}

export function bumpQueueDrain(
  tickets: Array<Record<string, unknown>>,
  start: number,
  bumpEvery: number
): string[] {
  if (!Number.isInteger(start) || start < 0) {
    throw new Error("the start minute is a non-negative whole number");
  }
  if (!Number.isInteger(bumpEvery) || bumpEvery <= 0) {
    throw new Error("the bump interval is a positive whole number");
  }
  if (!Array.isArray(tickets) || tickets.length === 0) {
    throw new Error("the batch is empty");
  }
  const pending: Ticket[] = [];
  const ids = new Set<string>();
  for (const raw of tickets) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a ticket must be a mapping");
    }
    const id = raw.id;
    if (typeof id !== "string" || id.length === 0) {
      throw new Error("a ticket needs an id");
    }
    if (ids.has(id)) {
      throw new Error("repeated ticket id: " + id);
    }
    ids.add(id);
    const filed = raw.filed;
    if (!Number.isInteger(filed) || (filed as number) < 0) {
      throw new Error("a filed minute is a non-negative whole number");
    }
    const grade = raw.grade;
    if (
      !Number.isInteger(grade) ||
      (grade as number) < 0 ||
      (grade as number) > CEILING
    ) {
      throw new Error("a grade runs from 0 to " + CEILING);
    }
    pending.push({ id, filed: filed as number, grade: grade as number });
  }

  const handled: string[] = [];
  let minute = start;
  while (pending.length > 0) {
    let pick = -1;
    for (let i = 0; i < pending.length; i++) {
      if (pending[i].filed > minute) {
        continue;
      }
      if (pick === -1) {
        pick = i;
        continue;
      }
      const here = urgency(pending[i], minute, bumpEvery);
      const held = urgency(pending[pick], minute, bumpEvery);
      if (here > held) {
        pick = i;
      } else if (here === held) {
        if (
          pending[i].filed < pending[pick].filed ||
          (pending[i].filed === pending[pick].filed &&
            pending[i].id < pending[pick].id)
        ) {
          pick = i;
        }
      }
    }
    if (pick !== -1) {
      handled.push(pending[pick].id);
      pending.splice(pick, 1);
    }
    minute += 1;
  }
  return handled;
}
