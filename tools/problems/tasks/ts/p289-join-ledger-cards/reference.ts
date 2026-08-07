type Field = { name: string; start: number; width: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function joinLedgerCards(
  cards: string[],
  layout: Field[],
): Record<string, string>[] {
  if (!Array.isArray(layout) || layout.length === 0) {
    throw new Error("layout must be a non-empty list");
  }
  const names = new Set<string>();
  const claimed = new Set<number>();
  let span = 0;
  for (const field of layout) {
    if (field === null || typeof field !== "object") {
      throw new Error("a layout entry must be a record");
    }
    if (typeof field.name !== "string" || field.name.length === 0) {
      throw new Error("a field name must be a non-empty string");
    }
    if (names.has(field.name)) {
      throw new Error("field names repeat: " + field.name);
    }
    names.add(field.name);
    if (!whole(field.start) || field.start < 1) {
      throw new Error("start must be an integer of at least 1: " + field.name);
    }
    if (!whole(field.width) || field.width < 1) {
      throw new Error("width must be an integer of at least 1: " + field.name);
    }
    for (let column = field.start; column < field.start + field.width; column++) {
      if (claimed.has(column)) {
        throw new Error("two fields claim column " + String(column));
      }
      claimed.add(column);
    }
    span = Math.max(span, field.start + field.width - 1);
  }

  if (!Array.isArray(cards) || cards.length === 0) {
    throw new Error("cards must be a non-empty list");
  }
  for (const card of cards) {
    if (typeof card !== "string") {
      throw new Error("cards must be a list of strings");
    }
    const mark = card.slice(0, 1);
    if (mark !== "=" && mark !== "+") {
      throw new Error("a card marker must be = or +");
    }
    if (card.length - 1 < span) {
      throw new Error("a card body stops short of column " + String(span));
    }
  }
  if (cards[0][0] !== "=") {
    throw new Error("the first card must open a record");
  }

  const records: Record<string, string>[] = [];
  for (const card of cards) {
    const values: Record<string, string> = {};
    for (const field of layout) {
      const raw = card.slice(field.start, field.start + field.width);
      values[field.name] = raw.replace(/\.+$/, "");
    }
    if (card[0] === "+") {
      const open = records[records.length - 1];
      for (const field of layout) {
        open[field.name] = open[field.name] + values[field.name];
      }
      continue;
    }
    records.push(values);
  }
  return records;
}
