/** Replay a notepad editing session: type, erase, replace, undo and redo. */
export function replayNotepad(commands: (string | number)[][]): string {
  const isCount = (value: number): boolean =>
    typeof value === "number" && Number.isInteger(value) && value > 0;
  let buffer = "";
  const past: string[] = [];
  let future: string[] = [];
  for (const command of commands) {
    if (!Array.isArray(command) || command.length < 2) {
      throw new Error("command must be an action and its payload");
    }
    const action = command[0];
    if (action === "type") {
      if (command.length !== 2) {
        throw new Error("type takes exactly one text");
      }
      const text = command[1];
      if (typeof text !== "string" || text.length === 0) {
        throw new Error("type text must be a non-empty string");
      }
      past.push(buffer);
      future = [];
      buffer += text;
    } else if (action === "erase") {
      if (command.length !== 2) {
        throw new Error("erase takes exactly one count");
      }
      const count = command[1] as number;
      if (!isCount(count)) {
        throw new Error("erase count must be a positive integer");
      }
      if (count > buffer.length) {
        throw new Error("erase count exceeds the buffer");
      }
      past.push(buffer);
      future = [];
      buffer = buffer.slice(0, buffer.length - count);
    } else if (action === "replace") {
      if (command.length !== 3) {
        throw new Error("replace takes an old and a new text");
      }
      const oldText = command[1];
      const newText = command[2];
      if (typeof oldText !== "string" || oldText.length === 0) {
        throw new Error("replace old text must be a non-empty string");
      }
      if (typeof newText !== "string") {
        throw new Error("replace new text must be a string");
      }
      const at = buffer.lastIndexOf(oldText);
      if (at === -1) {
        throw new Error("replace old text does not occur in the buffer");
      }
      past.push(buffer);
      future = [];
      buffer = buffer.slice(0, at) + newText + buffer.slice(at + oldText.length);
    } else if (action === "undo") {
      if (command.length !== 2) {
        throw new Error("undo takes exactly one count");
      }
      const count = command[1] as number;
      if (!isCount(count)) {
        throw new Error("undo count must be a positive integer");
      }
      if (count > past.length) {
        throw new Error("undo count exceeds the edits available");
      }
      for (let i = 0; i < count; i++) {
        future.push(buffer);
        buffer = past.pop() as string;
      }
    } else if (action === "redo") {
      if (command.length !== 2) {
        throw new Error("redo takes exactly one count");
      }
      const count = command[1] as number;
      if (!isCount(count)) {
        throw new Error("redo count must be a positive integer");
      }
      if (count > future.length) {
        throw new Error("redo count exceeds the edits available");
      }
      for (let i = 0; i < count; i++) {
        past.push(buffer);
        buffer = future.pop() as string;
      }
    } else {
      throw new Error("unknown action: " + String(action));
    }
  }
  return buffer;
}
