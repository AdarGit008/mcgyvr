export function charRun(text: string): number {
  let best = 0;
  let run = 0;
  for (let i = 0; i < text.length; i += 1) {
    run = i > 0 && text[i] === text[i - 1] ? run + 1 : 1;
    if (run > best) {
      best = run;
    }
  }
  return best;
}
