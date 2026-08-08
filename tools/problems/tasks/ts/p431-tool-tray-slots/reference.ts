const VERBS = ["touch", "pin", "drop"];

export function foldToolTray(slots: number, actions: string[][]): string[] {
  if (typeof slots !== "number" || !Number.isInteger(slots) || slots < 1) {
    throw new Error("slots must be a whole number of at least 1");
  }
  if (!Array.isArray(actions)) {
    throw new Error("the actions must be a list of pairs");
  }

  const order: string[] = [];
  const stuck = new Set<string>();

  for (const action of actions) {
    if (!Array.isArray(action) || action.length !== 2) {
      throw new Error("an action is a [verb, name] pair");
    }
    const verb = action[0];
    const name = action[1];
    if (typeof verb !== "string" || !VERBS.includes(verb)) {
      throw new Error("a verb is one of touch, pin and drop");
    }
    if (typeof name !== "string" || name.length === 0 || name.includes("*")) {
      throw new Error("a name must be a non-empty string free of asterisks");
    }

    const at = order.indexOf(name);
    if (verb === "touch") {
      if (at !== -1) {
        order.splice(at, 1);
        order.push(name);
        continue;
      }
      if (order.length >= slots) {
        const victim = order.find((held) => !stuck.has(held));
        if (victim === undefined) {
          continue;
        }
        order.splice(order.indexOf(victim), 1);
        stuck.delete(victim);
      }
      order.push(name);
    } else if (verb === "pin") {
      if (at !== -1) {
        stuck.add(name);
      }
    } else if (at !== -1) {
      order.splice(at, 1);
      stuck.delete(name);
    }
  }

  const shown: string[] = [];
  for (let index = order.length - 1; index >= 0; index--) {
    const name = order[index];
    shown.push(stuck.has(name) ? `*${name}` : name);
  }
  return shown;
}
