/** A chart with its twin rows squashed together. */

type Row = { label: string; mark: string; next: string[] };

export function squashRows(
  chart: Record<string, unknown>
): Record<string, unknown> {
  if (chart === null || typeof chart !== "object" || Array.isArray(chart)) {
    throw new Error("a chart must be a mapping");
  }
  const signals = chart.signals;
  if (!Array.isArray(signals) || signals.length === 0) {
    throw new Error("the signal list is empty");
  }
  const signalSeen = new Set<string>();
  for (const signal of signals) {
    if (typeof signal !== "string" || signal.length === 0) {
      throw new Error("a signal is a non-empty string");
    }
    if (signalSeen.has(signal)) {
      throw new Error("the signal " + signal + " is listed twice");
    }
    signalSeen.add(signal);
  }
  const raw = chart.rows;
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new Error("the chart holds no rows");
  }
  const rows: Row[] = [];
  const at = new Map<string, number>();
  for (const item of raw) {
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      throw new Error("a row must be a mapping");
    }
    const row = item as Record<string, unknown>;
    const label = row.label;
    if (typeof label !== "string" || label.length === 0) {
      throw new Error("a row needs a non-empty label");
    }
    if (at.has(label)) {
      throw new Error("two rows share the label " + label);
    }
    const mark = row.mark;
    if (typeof mark !== "string" || mark.length === 0) {
      throw new Error("a row needs a non-empty mark");
    }
    const next = row.next;
    if (!Array.isArray(next) || next.length !== signals.length) {
      throw new Error(label + " does not hold one next entry per signal");
    }
    at.set(label, rows.length);
    rows.push({ label, mark, next: next as string[] });
  }
  for (const row of rows) {
    for (const target of row.next) {
      if (typeof target !== "string" || !at.has(target)) {
        throw new Error(row.label + " leads to a row nobody declared");
      }
    }
  }
  const head = chart.head;
  if (typeof head !== "string" || !at.has(head)) {
    throw new Error("the head names no row");
  }

  const marks: string[] = [];
  let block = rows.map((row) => {
    let id = marks.indexOf(row.mark);
    if (id === -1) {
      id = marks.length;
      marks.push(row.mark);
    }
    return id;
  });
  let blocks = marks.length;
  for (;;) {
    const seen = new Map<string, number>();
    const next: number[] = [];
    for (let i = 0; i < rows.length; i++) {
      const parts = rows[i].next.map((target) =>
        String(block[at.get(target) as number])
      );
      const signature = block[i] + "|" + parts.join(",");
      if (!seen.has(signature)) {
        seen.set(signature, seen.size);
      }
      next.push(seen.get(signature) as number);
    }
    block = next;
    if (seen.size === blocks) {
      break;
    }
    blocks = seen.size;
  }

  const numbered = new Map<number, number>();
  const leaders: number[] = [];
  for (let i = 0; i < rows.length; i++) {
    if (!numbered.has(block[i])) {
      numbered.set(block[i], leaders.length);
      leaders.push(i);
    }
  }
  const folded = leaders.map((index, number) => ({
    at: number,
    mark: rows[index].mark,
    next: rows[index].next.map(
      (target) => numbered.get(block[at.get(target) as number]) as number
    ),
  }));
  return {
    entry: numbered.get(block[at.get(head) as number]) as number,
    rows: folded,
  };
}
