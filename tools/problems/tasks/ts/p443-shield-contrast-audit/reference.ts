const METALS = new Set(["or", "argent"]);
const COLOURS = new Set(["gules", "azure", "sable", "vert", "purpure"]);

function classOf(tincture: unknown): string {
  if (typeof tincture === "string" && METALS.has(tincture)) {
    return "metal";
  }
  if (typeof tincture === "string" && COLOURS.has(tincture)) {
    return "colour";
  }
  throw new Error(`unknown tincture ${String(tincture)}`);
}

/** Which figures fail to stand out from the field behind them. */
export function auditShieldContrast(
  shields: Record<string, any>[],
): Record<string, unknown>[] {
  if (!Array.isArray(shields)) {
    throw new Error("shields must be a list");
  }
  const labels = new Set<string>();
  const report: Record<string, unknown>[] = [];
  for (const shield of shields) {
    const label = shield.label;
    if (typeof label !== "string" || label.length === 0) {
      throw new Error("every shield needs a non-empty label");
    }
    if (labels.has(label)) {
      throw new Error(`two shields share the label ${label}`);
    }
    labels.add(label);

    const field = shield.field;
    if (!Array.isArray(field) || field.length < 1 || field.length > 2) {
      throw new Error(`the field of ${label} is not one or two tinctures`);
    }
    const fieldClasses = field.map(classOf);

    const borne = new Set<string>();
    const unsound: string[] = [];
    for (const charge of shield.charges) {
      const figure = charge.figure;
      if (borne.has(figure)) {
        throw new Error(`${label} bears ${figure} twice`);
      }
      borne.add(figure);
      const own = classOf(charge.tincture);
      const sharesName = field.indexOf(charge.tincture) !== -1;
      const contrasts = fieldClasses.some((each) => each !== own);
      if (sharesName || !contrasts) {
        unsound.push(figure);
      }
    }
    if (unsound.length > 0) {
      report.push({ label, unsound });
    }
  }
  return report;
}
