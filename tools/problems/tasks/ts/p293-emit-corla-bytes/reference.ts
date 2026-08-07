const SPOT = /^[a-z][a-z0-9_]*$/;

type Step = { code: number; width: number; value: number; spot: string | null };

function spotName(text: string): string {
  if (!text.startsWith(".") || !SPOT.test(text.slice(1))) {
    throw new Error("badly spelled spot: " + text);
  }
  return text.slice(1);
}

export function emitCorlaBytes(lines: string[]): number[] {
  if (!Array.isArray(lines)) {
    throw new Error("emitCorlaBytes expects a list of rows");
  }
  const spots = new Map<string, number>();
  const steps: Step[] = [];
  let tally = 0;
  for (const raw of lines) {
    if (typeof raw !== "string") {
      throw new Error("every row must be text");
    }
    const row = raw.trim();
    if (row === "" || row.startsWith("#")) {
      continue;
    }
    if (row.startsWith(".")) {
      const name = spotName(row);
      if (spots.has(name)) {
        throw new Error("spot named twice: " + name);
      }
      spots.set(name, tally);
      continue;
    }
    const parts = row.split(/\s+/);
    const keyword = parts[0];
    if (keyword === "NOP" || keyword === "STOP") {
      if (parts.length !== 1) {
        throw new Error("wrong count of arguments: " + row);
      }
      steps.push({ code: keyword === "NOP" ? 0 : 64, width: 1, value: 0, spot: null });
      tally += 1;
    } else if (keyword === "LOAD") {
      if (parts.length !== 2) {
        throw new Error("wrong count of arguments: " + row);
      }
      if (!/^(?:0|[1-9][0-9]*)$/.test(parts[1]) || Number(parts[1]) > 255) {
        throw new Error("v outside 0 to 255: " + parts[1]);
      }
      steps.push({ code: 16, width: 2, value: Number(parts[1]), spot: null });
      tally += 2;
    } else if (keyword === "GOTO" || keyword === "CALL") {
      if (parts.length !== 2) {
        throw new Error("wrong count of arguments: " + row);
      }
      steps.push({
        code: keyword === "GOTO" ? 32 : 48,
        width: 3,
        value: 0,
        spot: spotName(parts[1]),
      });
      tally += 3;
    } else {
      throw new Error("keyword nobody knows: " + row);
    }
  }
  const bytes: number[] = [];
  for (const step of steps) {
    if (step.spot === null) {
      bytes.push(step.code);
      if (step.width === 2) {
        bytes.push(step.value);
      }
      continue;
    }
    const seat = spots.get(step.spot);
    if (seat === undefined) {
      throw new Error("no row names spot: " + step.spot);
    }
    bytes.push(step.code, Math.floor(seat / 256), seat % 256);
  }
  return bytes;
}
