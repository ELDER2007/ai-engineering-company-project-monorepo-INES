// Random ids of the telemetry (`lib/telemetry/ids.ts`): UUID v4 as the contract's pattern requires, also in a browser
// context where `crypto.randomUUID` does not exist (plain http).
import { opaqueId, uuidV4 } from "@/lib/telemetry/ids";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const realCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
afterEach(() => {
  if (realCrypto) Object.defineProperty(globalThis, "crypto", realCrypto);
});
const useCrypto = (value: unknown) => Object.defineProperty(globalThis, "crypto", { value, configurable: true });

describe("uuidV4", () => {
  it("uses crypto.randomUUID when it exists", () => {
    useCrypto({ randomUUID: () => "11111111-1111-4111-8111-111111111111" });
    expect(uuidV4()).toBe("11111111-1111-4111-8111-111111111111");
  });

  it("builds a valid v4 from getRandomValues when randomUUID is missing (insecure context)", () => {
    useCrypto({ getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff) });
    const id = uuidV4();
    expect(id).toMatch(UUID_V4);
    expect(id).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff"); // version and variant bits forced
  });

  it("still returns a valid v4 with no crypto at all", () => {
    useCrypto(undefined);
    const ids = new Set(Array.from({ length: 50 }, uuidV4));
    expect(ids.size).toBe(50);
    for (const id of ids) expect(id).toMatch(UUID_V4);
  });

  it("two ids are never equal in a normal browser", () => {
    expect(uuidV4()).not.toBe(uuidV4());
    expect(uuidV4()).toMatch(UUID_V4);
  });
});

describe("opaqueId", () => {
  it.each([[12, "12"], ["INC-7", "INC-7"], ["a_b-c", "a_b-c"], ["x".repeat(128), "x".repeat(128)]])("accepts %p", (value, expected) => {
    expect(opaqueId(value)).toBe(expected);
  });
  it.each(["", "-leading", "_leading", "María López", "a b", "ana@example.com", "x".repeat(129), null, undefined, {}, [], true])(
    "drops %p: it may be a name or an e-mail, so it is never sent or cleaned",
    (value) => expect(opaqueId(value)).toBeNull(),
  );
});
