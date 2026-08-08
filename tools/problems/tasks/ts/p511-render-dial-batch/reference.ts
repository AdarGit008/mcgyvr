/** Dial strings for a batch of rows, and the tags of the rows that refuse. */
const BOOK: Record<string, { stem: string; cuts: number[] }> = {
  ashen: { stem: "8", cuts: [2, 2, 3] },
  brill: { stem: "", cuts: [5, 3] },
  cobal: { stem: "44", cuts: [3, 3] },
};

export function renderDialBatch(rows: unknown): Record<string, unknown> {
  if (!Array.isArray(rows)) throw new Error("the rows must be a list");
  const tags: string[] = [];
  for (const row of rows) {
    if (row === null || typeof row !== "object" || Array.isArray(row)) {
      throw new Error("a row must be a mapping");
    }
    const tag = (row as Record<string, unknown>).tag;
    if (typeof tag !== "string" || tag.length === 0) {
      throw new Error("a row needs a non-empty tag");
    }
    if (tags.includes(tag)) throw new Error("two rows carry the same tag");
    tags.push(tag);
  }

  const lines: Array<{ tag: string; dial: string }> = [];
  const bad: string[] = [];
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index] as Record<string, unknown>;
    const exchange = row.exchange;
    if (typeof exchange !== "string" || !Object.prototype.hasOwnProperty.call(BOOK, exchange)) {
      bad.push(tags[index]);
      continue;
    }
    const line = row.line;
    if (typeof line !== "string" || !/^[0-9]+$/.test(line)) {
      bad.push(tags[index]);
      continue;
    }
    const plan = BOOK[exchange];
    const wanted = plan.cuts.reduce((sum, cut) => sum + cut, 0);
    if (line.length !== wanted) {
      bad.push(tags[index]);
      continue;
    }
    const parts: string[] = [];
    let cursor = 0;
    for (const cut of plan.cuts) {
      parts.push(line.slice(cursor, cursor + cut));
      cursor += cut;
    }
    const body = parts.join("-");
    lines.push({ tag: tags[index], dial: plan.stem === "" ? body : "(" + plan.stem + ")" + body });
  }

  return { lines, bad };
}
