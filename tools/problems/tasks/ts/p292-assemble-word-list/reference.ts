type Piece = { word: number; marker: string | null };

const MARKER_LINE = /^([a-z][a-z0-9_]*):$/;
const MARKER_NAME = /^[a-z][a-z0-9_]*$/;
const HEAD = /^([A-Z]+)(?:\s+(\S.*))?$/;

function register(text: string): number {
  const found = /^r([0-7])$/.exec(text);
  if (found === null) {
    throw new Error("bad register: " + text);
  }
  return Number(found[1]);
}

function immediate(text: string): number {
  if (!/^(?:0|[1-9][0-9]*)$/.test(text)) {
    throw new Error("bad immediate: " + text);
  }
  const value = Number(text);
  if (value > 255) {
    throw new Error("immediate outside 0 through 255: " + text);
  }
  return value;
}

function expect(operands: string[], count: number, mnemonic: string): void {
  if (operands.length !== count) {
    throw new Error(mnemonic + " takes " + count + " operands");
  }
}

export function assembleWordList(lines: string[]): number[] {
  if (!Array.isArray(lines)) {
    throw new Error("assembleWordList expects a list of lines");
  }
  const pieces: Piece[] = [];
  const markers = new Map<string, number>();
  for (const raw of lines) {
    if (typeof raw !== "string") {
      throw new Error("every source line must be a string");
    }
    const line = raw.trim();
    if (line === "" || line.startsWith(";")) {
      continue;
    }
    const planted = MARKER_LINE.exec(line);
    if (planted !== null) {
      if (markers.has(planted[1])) {
        throw new Error("marker planted twice: " + planted[1]);
      }
      markers.set(planted[1], pieces.length);
      continue;
    }
    const head = HEAD.exec(line);
    if (head === null) {
      throw new Error("line the format does not cover: " + line);
    }
    const mnemonic = head[1];
    const operands =
      head[2] === undefined ? [] : head[2].split(",").map((part) => part.trim());
    if (mnemonic === "SET") {
      expect(operands, 2, "SET");
      pieces.push({
        word: 4096 + 256 * register(operands[0]) + immediate(operands[1]),
        marker: null,
      });
    } else if (mnemonic === "ADD") {
      expect(operands, 2, "ADD");
      pieces.push({
        word: 8192 + 256 * register(operands[0]) + register(operands[1]),
        marker: null,
      });
    } else if (mnemonic === "JZ") {
      expect(operands, 2, "JZ");
      const target = operands[1];
      if (!MARKER_NAME.test(target)) {
        throw new Error("bad marker name: " + target);
      }
      pieces.push({ word: 12288 + 256 * register(operands[0]), marker: target });
    } else if (mnemonic === "HALT") {
      expect(operands, 0, "HALT");
      pieces.push({ word: 16384, marker: null });
    } else {
      throw new Error("unknown mnemonic: " + mnemonic);
    }
  }
  const words: number[] = [];
  for (let at = 0; at < pieces.length; at++) {
    const piece = pieces[at];
    if (piece.marker === null) {
      words.push(piece.word);
      continue;
    }
    const seat = markers.get(piece.marker);
    if (seat === undefined) {
      throw new Error("no line plants marker: " + piece.marker);
    }
    const distance = seat - (at + 1);
    if (distance < -128 || distance > 127) {
      throw new Error("distance outside -128 through 127: " + distance);
    }
    words.push(piece.word + (distance < 0 ? distance + 256 : distance));
  }
  return words;
}
