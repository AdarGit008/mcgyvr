function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function gaugeMacroDepth(
  macros: Record<string, unknown>[],
  bound: number,
): string[] {
  if (!whole(bound) || bound < 0) {
    throw new Error("the bound is not whole or falls below nought");
  }
  if (!Array.isArray(macros)) {
    throw new Error("gaugeMacroDepth expects a list of macros");
  }

  const arity = new Map<string, number>();
  const calls = new Map<string, string[]>();
  const counts = new Map<string, number[]>();
  for (const macro of macros) {
    if (!isRecord(macro)) {
      throw new Error("a macro is not a record");
    }
    if (Object.keys(macro).sort().join(",") !== "arity,calls,name") {
      throw new Error("a macro's keys are not exactly the three named");
    }
    const name = macro["name"];
    if (typeof name !== "string" || !/^[a-z][a-z0-9]*$/.test(name)) {
      throw new Error("a macro name is malformed");
    }
    if (arity.has(name)) {
      throw new Error("two macros answer to one name");
    }
    const taken = macro["arity"];
    if (!whole(taken) || Number(taken) < 0 || Number(taken) > 9) {
      throw new Error("an arity is not whole or falls outside nought through nine");
    }
    const made = macro["calls"];
    if (!Array.isArray(made)) {
      throw new Error("the calls are not a list");
    }
    const named: string[] = [];
    const handed: number[] = [];
    for (const call of made) {
      if (!Array.isArray(call) || call.length !== 2) {
        throw new Error("a call is not a list of exactly two entries");
      }
      if (typeof call[0] !== "string" || call[0].length === 0) {
        throw new Error("a called name is not a non-empty string");
      }
      if (!whole(call[1]) || Number(call[1]) < 0) {
        throw new Error("a call's argument count is not whole or falls below nought");
      }
      named.push(call[0]);
      handed.push(Number(call[1]));
    }
    arity.set(name, Number(taken));
    calls.set(name, named);
    counts.set(name, handed);
  }

  for (const [name, named] of calls) {
    const handed = counts.get(name)!;
    for (let i = 0; i < named.length; i++) {
      if (!arity.has(named[i])) {
        throw new Error("a call names a macro that was never declared");
      }
      if (handed[i] !== arity.get(named[i])) {
        throw new Error("a call hands over arguments the called macro does not take");
      }
    }
  }

  const LOOSE = -1;
  const state = new Map<string, number>();
  const memo = new Map<string, number>();

  const resolve = (name: string): number => {
    if (state.get(name) === 1) {
      return LOOSE;
    }
    if (state.get(name) === 2) {
      return memo.get(name)!;
    }
    state.set(name, 1);
    let deepest = 0;
    let loose = false;
    for (const callee of calls.get(name)!) {
      const found = resolve(callee);
      if (found === LOOSE) {
        loose = true;
      } else if (found + 1 > deepest) {
        deepest = found + 1;
      }
    }
    state.set(name, 2);
    const answer = loose ? LOOSE : deepest;
    memo.set(name, answer);
    return answer;
  };

  const names = [...arity.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  return names.map((name) => {
    const found = resolve(name);
    if (found === LOOSE) {
      return `${name} cyclic`;
    }
    return found > bound ? `${name} over` : `${name} ${found}`;
  });
}
