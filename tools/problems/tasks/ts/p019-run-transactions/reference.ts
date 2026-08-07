export function runTransactions(commands: string[]): Record<string, string> {
  const base: Record<string, string> = {};
  const layers: Map<string, string | null>[] = [];

  const applyToBase = (key: string, value: string | null): void => {
    if (value === null) {
      delete base[key];
    } else {
      base[key] = value;
    }
  };

  for (const command of commands) {
    const parts = command.split(" ");
    const verb = parts[0];
    if (verb === "set") {
      if (parts.length !== 3) {
        throw new Error(`set needs a key and a value: ${command}`);
      }
      if (layers.length > 0) {
        layers[layers.length - 1].set(parts[1], parts[2]);
      } else {
        base[parts[1]] = parts[2];
      }
    } else if (verb === "unset") {
      if (parts.length !== 2) {
        throw new Error(`unset needs exactly a key: ${command}`);
      }
      if (layers.length > 0) {
        layers[layers.length - 1].set(parts[1], null);
      } else {
        delete base[parts[1]];
      }
    } else if (verb === "begin") {
      if (parts.length !== 1) {
        throw new Error(`begin takes no parts: ${command}`);
      }
      layers.push(new Map());
    } else if (verb === "commit") {
      if (parts.length !== 1) {
        throw new Error(`commit takes no parts: ${command}`);
      }
      const top = layers.pop();
      if (top === undefined) {
        throw new Error("commit with no open transaction");
      }
      if (layers.length > 0) {
        const below = layers[layers.length - 1];
        for (const [key, value] of top) {
          below.set(key, value);
        }
      } else {
        for (const [key, value] of top) {
          applyToBase(key, value);
        }
      }
    } else if (verb === "rollback") {
      if (parts.length !== 1) {
        throw new Error(`rollback takes no parts: ${command}`);
      }
      if (layers.pop() === undefined) {
        throw new Error("rollback with no open transaction");
      }
    } else {
      throw new Error(`unknown verb in: ${command}`);
    }
  }
  if (layers.length > 0) {
    throw new Error("a transaction is still open");
  }
  return base;
}
