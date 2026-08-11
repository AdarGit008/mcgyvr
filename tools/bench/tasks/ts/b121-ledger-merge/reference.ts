/** Three-way ledger merge: apply both sides' edits against a common base. */

function readLedger(pairs: [string, number][]): Map<string, number> {
  if (!Array.isArray(pairs)) {
    throw new Error("a ledger must be a list of [account, cents] pairs");
  }
  const ledger = new Map<string, number>();
  for (const pair of pairs) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("a ledger entry must be an [account, cents] pair");
    }
    const [account, cents] = pair;
    if (typeof account !== "string" || account === "") {
      throw new Error("account name must be a non-empty string");
    }
    if (!Number.isInteger(cents)) {
      throw new Error("cents must be an integer");
    }
    if (ledger.has(account)) {
      throw new Error(`account repeated: ${account}`);
    }
    ledger.set(account, cents);
  }
  return ledger;
}

export function mergeLedgers(
  base: [string, number][],
  ours: [string, number][],
  theirs: [string, number][],
): [string, number][] {
  const before = readLedger(base);
  const left = readLedger(ours);
  const right = readLedger(theirs);
  const names = new Set([...before.keys(), ...left.keys(), ...right.keys()]);
  const merged: [string, number][] = [];
  for (const name of [...names].sort()) {
    const inBase = before.has(name);
    const inLeft = left.has(name);
    const inRight = right.has(name);
    if (inBase && inLeft && inRight) {
      const start = before.get(name) as number;
      const leftDelta = (left.get(name) as number) - start;
      const rightDelta = (right.get(name) as number) - start;
      merged.push([name, start + leftDelta + rightDelta]);
    } else if (!inBase && inLeft && inRight) {
      const added = (left.get(name) as number) + (right.get(name) as number);
      merged.push([name, added]);
    } else if (!inBase && (inLeft || inRight)) {
      const side = inLeft ? left : right;
      merged.push([name, side.get(name) as number]);
    } else if (inBase && (inLeft || inRight)) {
      const side = inLeft ? left : right;
      const survivor = side.get(name) as number;
      if (survivor !== before.get(name)) {
        merged.push([name, survivor]);
      }
    }
  }
  return merged;
}
