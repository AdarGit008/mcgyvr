export function stageAttrition(
  specimens: Array<Record<string, unknown>>,
  stages: Array<Record<string, unknown>>,
): [string, number][] {
  const seen = new Set<string>();
  for (const stage of stages) {
    const name = stage.stage;
    if (typeof name !== "string" || name === "") {
      throw new Error("stage name must be a non-empty string");
    }
    if (name === "through") {
      throw new Error('a stage may not be named "through"');
    }
    if (seen.has(name)) {
      throw new Error(`stage name repeated: ${name}`);
    }
    seen.add(name);
    const low = stage.low as number | null;
    const high = stage.high as number | null;
    if (low !== null && high !== null && low > high) {
      throw new Error("low exceeds high");
    }
  }
  const fails = (specimen: Record<string, unknown>, stage: Record<string, unknown>): boolean => {
    const value = specimen[stage.field as string];
    if (typeof value !== "number") {
      return true;
    }
    const low = stage.low as number | null;
    const high = stage.high as number | null;
    return (low !== null && value < low) || (high !== null && value > high);
  };
  const counts = new Map<string, number>();
  for (const stage of stages) {
    counts.set(stage.stage as string, 0);
  }
  let through = 0;
  for (const specimen of specimens) {
    const first = stages.find((stage) => fails(specimen, stage));
    if (first === undefined) {
      through += 1;
    } else {
      const name = first.stage as string;
      counts.set(name, counts.get(name)! + 1);
    }
  }
  const pairs: [string, number][] = [...counts.entries()].map(
    ([name, left]) => [name, left] as [string, number],
  );
  pairs.push(["through", through]);
  return pairs;
}
