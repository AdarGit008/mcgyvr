export function toggleRun(steps: string[]): boolean {
  let state = false;
  for (const step of steps) {
    if (step === "on") {
      state = true;
    } else if (step === "off") {
      state = false;
    } else if (step === "flip") {
      state = !state;
    }
  }
  return state;
}
