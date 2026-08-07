const OFFSET: Record<string, number> = {
  C: 0,
  D: 2,
  E: 4,
  F: 5,
  G: 7,
  A: 9,
  B: 11,
};

const SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
const SHAPE = /^[A-G](#|b)?[0-9]$/;

export function shiftNoteLine(
  notes: any[],
  shift: number,
  spelling: string,
): string[] {
  if (!Array.isArray(notes)) {
    throw new Error("the notes must be a list");
  }
  if (typeof shift !== "number" || !Number.isInteger(shift)) {
    throw new Error("the shift must be a whole number");
  }
  if (spelling !== "sharp" && spelling !== "flat") {
    throw new Error("the spelling is either sharp or flat");
  }
  const table = spelling === "sharp" ? SHARP : FLAT;
  const shifted: string[] = [];
  for (const note of notes) {
    if (typeof note !== "string" || !SHAPE.test(note)) {
      throw new Error("a note must be a letter, an optional sign and a digit");
    }
    const letter = note[0];
    const sign = note.length === 3 ? note[1] : "";
    const octave = Number(note[note.length - 1]);
    let seat = 12 * octave + OFFSET[letter];
    if (sign === "#") seat += 1;
    if (sign === "b") seat -= 1;
    const landed = seat + shift;
    const home = Math.floor(landed / 12);
    if (home < 0 || home > 9) {
      throw new Error("the shifted note lands outside octaves 0 to 9");
    }
    const leftover = ((landed % 12) + 12) % 12;
    shifted.push(table[leftover] + String(home));
  }
  return shifted;
}
