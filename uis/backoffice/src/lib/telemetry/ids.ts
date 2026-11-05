// Random identifiers for the telemetry. UUID v4 as the contract requires (pattern `...-4xxx-[89ab]xxx-...`).

export function uuidV4(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  // `randomUUID` only exists in secure contexts (https, localhost): a plain-http intranet still needs ids.
  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === "function") c.getRandomValues(bytes);
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

/**
 * An id as the contract accepts it (`$defs/id`: letters, digits, `_` and `-`, up to 128, starting with a letter or digit), or null.
 * An id that would not fit may be something else (a name typed into a field): it is dropped, never sent or "cleaned".
 */
export function opaqueId(value: unknown): string | null {
  const text = typeof value === "number" ? String(value) : value;
  return typeof text === "string" && text.length <= 128 && /^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(text) ? text : null;
}
