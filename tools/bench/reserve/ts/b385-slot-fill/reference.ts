/** Labels laid across a board of a fixed number of slots. */
export function slotFill(labels: string[], slots: number): string[] {
  const board: string[] = [];
  for (let i = 0; i < slots; i += 1) {
    if (i < labels.length) {
      if (labels[i] === "") {
        throw new Error("a label must not be empty");
      }
      board.push(labels[i]);
    } else {
      board.push("");
    }
  }
  return board;
}
