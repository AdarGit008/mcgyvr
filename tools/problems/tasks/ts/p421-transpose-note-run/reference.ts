const LADDER = ["C", "D", "E", "F", "G", "A", "B"];
const OFFSETS = [0, 2, 4, 5, 7, 9, 11];
const NOTE = /^[A-G](##|#|bb|b)?[0-9]$/;
const STAMP = /^[A-G](#|b)$/;
const SIGNS: Record<number, string> = {
  "-2": "bb",
  "-1": "b",
  0: "",
  1: "#",
  2: "##",
};

function signWorth(run: string): number {
  if (run === "") return 0;
  return run[0] === "#" ? run.length : -run.length;
}

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function transposeNoteRun(
  notes: any[],
  rung: number,
  size: number,
  key: any[],
): string[] {
  if (!Array.isArray(notes)) {
    throw new Error("the notes must be a list");
  }
  if (!whole(rung) || !whole(size)) {
    throw new Error("the rung and the size must be whole numbers");
  }
  if (!Array.isArray(key)) {
    throw new Error("the key must be a list");
  }
  const stamps = new Map<string, number>();
  for (const stamp of key) {
    if (typeof stamp !== "string" || !STAMP.test(stamp)) {
      throw new Error("a stamp is a letter with exactly one sign");
    }
    if (stamps.has(stamp[0])) {
      throw new Error("a letter is stamped twice");
    }
    stamps.set(stamp[0], signWorth(stamp[1]));
  }

  const moved: string[] = [];
  for (const note of notes) {
    if (typeof note !== "string" || !NOTE.test(note)) {
      throw new Error("a note is a letter, up to two signs and a digit");
    }
    const letter = note[0];
    const run = note.slice(1, note.length - 1);
    const octave = Number(note[note.length - 1]);
    const worth = run === "" ? (stamps.get(letter) ?? 0) : signWorth(run);
    const place = LADDER.indexOf(letter);
    const pitch = 12 * octave + OFFSETS[place] + worth;

    const walked = place + rung;
    const carry = Math.floor(walked / 7);
    const landedPlace = ((walked % 7) + 7) % 7;
    const home = octave + carry;
    if (home < 0 || home > 9) {
      throw new Error("the moved note falls outside octaves 0 to 9");
    }
    const bare = 12 * home + OFFSETS[landedPlace];
    const needed = pitch + size - bare;
    if (needed < -2 || needed > 2) {
      throw new Error("the moved note would need more than two signs");
    }
    moved.push(LADDER[landedPlace] + SIGNS[needed] + String(home));
  }
  return moved;
}
