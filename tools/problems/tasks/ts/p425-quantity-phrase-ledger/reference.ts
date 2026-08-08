const WORD = /^[a-z]+$/;

function readLexicon(lexicon: Record<string, string>): Map<number, string> {
  if (
    lexicon === null ||
    typeof lexicon !== "object" ||
    Array.isArray(lexicon)
  ) {
    throw new Error("the lexicon must be a mapping");
  }
  const figures = Object.keys(lexicon);
  if (figures.length < 2) {
    throw new Error("the lexicon must reach at least as far as 1");
  }
  const table = new Map<number, string>();
  for (let n = 0; n < figures.length; n++) {
    const key = String(n);
    if (!Object.prototype.hasOwnProperty.call(lexicon, key)) {
      throw new Error("the lexicon's figures must run on without a gap");
    }
    const word = lexicon[key];
    if (typeof word !== "string" || !WORD.test(word)) {
      throw new Error("a lexicon word must be a run of lowercase letters");
    }
    table.set(n, word);
  }
  return table;
}

export function phraseQuantityLedger(
  entries: (string | number)[][],
  lexicon: Record<string, string>,
): string {
  const table = readLexicon(lexicon);
  if (!Array.isArray(entries)) {
    throw new Error("the ledger must be a list of triples");
  }

  const order: string[] = [];
  const totals = new Map<string, number>();
  const plural = new Map<string, string>();
  for (const triple of entries) {
    if (!Array.isArray(triple) || triple.length !== 3) {
      throw new Error("a ledger line is a [tally, one, many] triple");
    }
    const tally = triple[0];
    const one = triple[1];
    const many = triple[2];
    if (
      typeof tally !== "number" ||
      !Number.isInteger(tally) ||
      tally < 0 ||
      tally > 999
    ) {
      throw new Error("a tally must be a whole number from 0 through 999");
    }
    for (const wording of [one, many]) {
      if (typeof wording !== "string" || !WORD.test(wording)) {
        throw new Error("a wording must be a run of lowercase letters");
      }
    }
    const key = one as string;
    if (!totals.has(key)) {
      order.push(key);
      totals.set(key, 0);
      plural.set(key, many as string);
    } else if (plural.get(key) !== many) {
      throw new Error(`two ledger lines disagree on the many wording of ${key}`);
    }
    totals.set(key, (totals.get(key) as number) + tally);
  }

  const parts: string[] = [];
  for (const key of order) {
    const total = totals.get(key) as number;
    if (total === 0) {
      continue;
    }
    const figure = table.has(total) ? (table.get(total) as string) : String(total);
    const wording = total === 1 ? key : (plural.get(key) as string);
    parts.push(`${figure} ${wording}`);
  }

  if (parts.length === 0) {
    return "nothing at all";
  }
  if (parts.length === 1) {
    return parts[0];
  }
  if (parts.length === 2) {
    return `${parts[0]} and ${parts[1]}`;
  }
  return `${parts.slice(0, -1).join(", ")}, and ${parts[parts.length - 1]}`;
}
