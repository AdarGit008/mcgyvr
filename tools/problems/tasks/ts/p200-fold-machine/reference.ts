function nameList(value: unknown, what: string, allowEmpty: boolean): string[] {
  if (!Array.isArray(value)) {
    throw new Error(what + " must be a list");
  }
  if (value.length === 0 && !allowEmpty) {
    throw new Error(what + " must not be empty");
  }
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (typeof item !== "string" || item.length === 0) {
      throw new Error(what + " holds something that is not a non-empty string");
    }
    if (seen.has(item)) {
      throw new Error(what + " names " + item + " twice");
    }
    seen.add(item);
    out.push(item);
  }
  return out;
}

export function foldMachine(
  machine: Record<string, unknown>
): Record<string, unknown> {
  if (machine === null || typeof machine !== "object" || Array.isArray(machine)) {
    throw new Error("a machine must be a mapping");
  }
  const alphabet = nameList(machine.alphabet, "the alphabet", false);
  const states = nameList(machine.states, "the state list", false);
  const stateSet = new Set(states);
  const symbolSet = new Set(alphabet);
  const start = machine.start;
  if (typeof start !== "string" || !stateSet.has(start)) {
    throw new Error("the start is not a listed state");
  }
  const accepting = new Set(nameList(machine.accepting, "the accepting list", true));
  for (const name of accepting) {
    if (!stateSet.has(name)) {
      throw new Error(name + " accepts but is not a listed state");
    }
  }
  const moves = machine.moves;
  if (!Array.isArray(moves)) {
    throw new Error("the moves must be a list");
  }
  const delta = new Map<string, Map<string, string>>();
  for (const state of states) {
    delta.set(state, new Map<string, string>());
  }
  for (const move of moves) {
    if (!Array.isArray(move) || move.length !== 3) {
      throw new Error("a move is three elements");
    }
    const [from, symbol, to] = move as [unknown, unknown, unknown];
    if (typeof from !== "string" || !stateSet.has(from)) {
      throw new Error("a move leaves an undeclared state");
    }
    if (typeof to !== "string" || !stateSet.has(to)) {
      throw new Error("a move lands on an undeclared state");
    }
    if (typeof symbol !== "string" || !symbolSet.has(symbol)) {
      throw new Error("a move carries an undeclared symbol");
    }
    const row = delta.get(from) as Map<string, string>;
    if (row.has(symbol)) {
      throw new Error(from + " has two moves on " + symbol);
    }
    row.set(symbol, to);
  }
  for (const state of states) {
    for (const symbol of alphabet) {
      if (!(delta.get(state) as Map<string, string>).has(symbol)) {
        throw new Error(state + " has no move on " + symbol);
      }
    }
  }

  const reached = new Set<string>([start]);
  const frontier = [start];
  while (frontier.length > 0) {
    const state = frontier.shift() as string;
    for (const symbol of alphabet) {
      const next = (delta.get(state) as Map<string, string>).get(
        symbol
      ) as string;
      if (!reached.has(next)) {
        reached.add(next);
        frontier.push(next);
      }
    }
  }
  const live = states.filter((state) => reached.has(state));

  let block = new Map<string, number>();
  for (const state of live) {
    block.set(state, accepting.has(state) ? 1 : 0);
  }
  let blocks = new Set(block.values()).size;
  for (;;) {
    const seen = new Map<string, number>();
    const next = new Map<string, number>();
    for (const state of live) {
      const row = delta.get(state) as Map<string, string>;
      const parts = alphabet.map((symbol) =>
        String(block.get(row.get(symbol) as string))
      );
      const signature = block.get(state) + "|" + parts.join(",");
      if (!seen.has(signature)) {
        seen.set(signature, seen.size);
      }
      next.set(state, seen.get(signature) as number);
    }
    block = next;
    if (seen.size === blocks) {
      break;
    }
    blocks = seen.size;
  }

  const representative = new Map<number, string>();
  for (const state of live) {
    const id = block.get(state) as number;
    if (!representative.has(id)) {
      representative.set(id, state);
    }
  }
  const numbered = new Map<number, number>();
  const order: number[] = [];
  const startBlock = block.get(start) as number;
  numbered.set(startBlock, 0);
  order.push(startBlock);
  for (let i = 0; i < order.length; i++) {
    const rep = representative.get(order[i]) as string;
    const row = delta.get(rep) as Map<string, string>;
    for (const symbol of alphabet) {
      const target = block.get(row.get(symbol) as string) as number;
      if (!numbered.has(target)) {
        numbered.set(target, order.length);
        order.push(target);
      }
    }
  }

  const accepts: number[] = [];
  const foldedMoves: Array<[number, string, number]> = [];
  for (let i = 0; i < order.length; i++) {
    const rep = representative.get(order[i]) as string;
    if (accepting.has(rep)) {
      accepts.push(i);
    }
    const row = delta.get(rep) as Map<string, string>;
    for (const symbol of alphabet) {
      const target = block.get(row.get(symbol) as string) as number;
      foldedMoves.push([i, symbol, numbered.get(target) as number]);
    }
  }
  return { size: order.length, start: 0, accepting: accepts, moves: foldedMoves };
}
