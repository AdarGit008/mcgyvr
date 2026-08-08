type Charge = { count: number; charge: string; tincture: string };
type Blazon = {
  field: { cut: string; tinctures: string[] };
  charges: Charge[];
};

const TINCTURES = new Set([
  "or",
  "argent",
  "gules",
  "azure",
  "sable",
  "vert",
  "purpure",
]);

const COUNTS: Record<string, number> = {
  a: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
};

const CHARGES = new Set(["lion", "mullet", "crescent", "rose", "bend"]);

function tincture(word: string): string {
  if (!TINCTURES.has(word)) {
    throw new Error(`unknown tincture ${word}`);
  }
  return word;
}

export function readBlazonLine(line: string): Record<string, unknown> {
  if (typeof line !== "string") {
    throw new Error("blazon line must be a string");
  }
  if (line.length === 0) {
    throw new Error("blazon line is empty");
  }
  const clauses = line.split("; ");
  for (const clause of clauses) {
    if (clause.length === 0) {
      throw new Error("blazon line has an empty clause");
    }
  }

  const head = clauses[0].split(" ");
  let field: { cut: string; tinctures: string[] };
  if (head.length === 1) {
    field = { cut: "plain", tinctures: [tincture(head[0])] };
  } else if (head.length === 5) {
    if (head[0] !== "parted" || head[3] !== "and") {
      throw new Error("malformed field clause");
    }
    if (head[1] !== "pale" && head[1] !== "fess") {
      throw new Error(`unknown division ${head[1]}`);
    }
    const left = tincture(head[2]);
    const right = tincture(head[4]);
    if (left === right) {
      throw new Error("a parted field needs two different tinctures");
    }
    field = { cut: head[1], tinctures: [left, right] };
  } else {
    throw new Error("malformed field clause");
  }

  const charges: Charge[] = [];
  const named = new Set<string>();
  for (const clause of clauses.slice(1)) {
    const words = clause.split(" ");
    if (words.length !== 3) {
      throw new Error("a charge clause is three words");
    }
    const count = COUNTS[words[0]];
    if (count === undefined) {
      throw new Error(`unknown count ${words[0]}`);
    }
    let bare = words[1];
    if (count > 1) {
      if (!bare.endsWith("s")) {
        throw new Error("a count above one needs the plural word");
      }
      bare = bare.slice(0, -1);
    }
    if (!CHARGES.has(bare)) {
      throw new Error(`unknown charge word ${words[1]}`);
    }
    if (named.has(bare)) {
      throw new Error(`charge word ${bare} is named twice`);
    }
    named.add(bare);
    charges.push({ count, charge: bare, tincture: tincture(words[2]) });
  }

  const result: Blazon = { field, charges };
  return result as unknown as Record<string, unknown>;
}
