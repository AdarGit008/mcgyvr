// The zero-dependency subset validator — extracted from descriptor.mjs (M4a) so the
// record schemas share the exact engine the descriptor uses. A small, deterministic
// subset of JSON Schema — enough for the descriptor + records and no more: type, enum,
// pattern, minLength, required, additionalProperties:false, nested properties, array
// items. Messages are input-derived only (no paths/dates) so golden pins stay stable.
// Keys prefixed with _ are inline notes and are ignored (the config-file convention).
const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k)
function matchesType(v, t) {
  switch (t) {
    case 'object':  return v !== null && typeof v === 'object' && !Array.isArray(v)
    case 'array':   return Array.isArray(v)
    case 'integer': return typeof v === 'number' && Number.isInteger(v)
    case 'number':  return typeof v === 'number'
    case 'string':  return typeof v === 'string'
    case 'boolean': return typeof v === 'boolean'
    default:        return true
  }
}
const describe = v => (v !== null && typeof v === 'object') ? (Array.isArray(v) ? 'array' : 'object') : JSON.stringify(v)
const childPath = (where, k) => where ? `${where}.${k}` : k

export function validateAgainst(value, schema, where, errors) {
  if (schema.type && !matchesType(value, schema.type)) {
    errors.push(`${where || 'descriptor'} must be ${schema.type} (got ${describe(value)})`)
    return // a type mismatch cascades into noise — stop at this node
  }
  if (schema.enum && !schema.enum.includes(value)) errors.push(`${where} must be one of ${schema.enum.join('|')} (got ${describe(value)})`)
  if (schema.pattern && typeof value === 'string' && !new RegExp(schema.pattern).test(value)) errors.push(`${where} must match ${schema.pattern} (got ${describe(value)})`)
  if (schema.minLength != null && typeof value === 'string' && value.length < schema.minLength) errors.push(`${where} must be non-empty`)
  // maxLength/maxItems: bound attacker-influenced strings/arrays (a lanes.families glob
  // rides into globToRe — an unbounded one is ReDoS fuel; globToRe also collapses runs,
  // so this is defense in depth). Messages stay input-free for stable golden pins.
  if (schema.maxLength != null && typeof value === 'string' && value.length > schema.maxLength) errors.push(`${where} must be at most ${schema.maxLength} characters`)
  if (schema.maxItems != null && Array.isArray(value) && value.length > schema.maxItems) errors.push(`${where} must have at most ${schema.maxItems} items`)
  if (schema.type === 'object' && matchesType(value, 'object')) {
    const props = schema.properties || {}
    for (const req of (schema.required || [])) if (!(req in value)) errors.push(`${where ? where + ': ' : ''}missing required field '${req}'`)
    for (const k of Object.keys(value)) {
      if (k.startsWith('_')) continue // inline comment keys, ignored (matches the config-file convention)
      // hasOwn, not `in`: a field named __proto__/constructor/toString would match the
      // prototype chain and read as "known", skipping the unknown-field error entirely
      if (!hasOwn(props, k)) { if (schema.additionalProperties === false) errors.push(`'${childPath(where, k)}' is not a known field`); continue }
      validateAgainst(value[k], props[k], childPath(where, k), errors)
    }
  }
  if (schema.type === 'array' && Array.isArray(value) && schema.items) value.forEach((el, i) => validateAgainst(el, schema.items, `${where}[${i}]`, errors))
}
