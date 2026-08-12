const MOVES: Record<string, Record<string, string>> = {
  lowered: { raise: "raised" },
  raised: { lower: "lowered", lock: "locked" },
  locked: { unlock: "raised" },
};

export function driveBridge(commands: string[]): string {
  if (!Array.isArray(commands)) throw new Error("driveBridge expects a list of commands");
  let state = "lowered";
  for (const command of commands) {
    if (!["raise", "lower", "lock", "unlock"].includes(command)) throw new Error("unknown command word");
    const next = MOVES[state][command];
    if (next === undefined) throw new Error(command + " is not allowed while " + state);
    state = next;
  }
  return state;
}
