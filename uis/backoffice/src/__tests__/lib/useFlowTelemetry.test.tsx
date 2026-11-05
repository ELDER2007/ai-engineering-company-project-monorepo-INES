// The life of one form attempt as telemetry (`lib/telemetry/useFlow.ts`): started at the first interaction, one step per
// milestone, completed on confirmation, cancelled explicitly. `track` is mocked; the clock is controlled.
//
// Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
import { renderHook } from "@testing-library/react";
import { track } from "@/lib/telemetry";
import { useFlowTelemetry } from "@/lib/telemetry/useFlow";

jest.mock("@/lib/telemetry", () => ({ track: jest.fn() }));
const trackMock = jest.mocked(track);
const sent = () => trackMock.mock.calls.map(([type, props, options]) => ({ type, props: props as Record<string, unknown>, options }));
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

let now = 1_000;
beforeEach(() => {
  now = 1_000;
  jest.spyOn(performance, "now").mockImplementation(() => now);
});
afterEach(() => jest.restoreAllMocks());

describe("useFlowTelemetry", () => {
  describe("happy path", () => {
    it("tells the whole story of a successful attempt with ONE flow id and a monotonic elapsed time", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));

      result.current.begin();
      now += 4_000;
      result.current.step("validated");
      now += 10;
      result.current.step("submitted", "req-1");
      now += 300;
      result.current.complete("req-1");

      const events = sent();
      expect(events.map((e) => [e.type, e.props.step, e.props.elapsed_ms])).toEqual([
        ["flow_started", "form", 0],
        ["flow_step_completed", "validated", 4000],
        ["flow_step_completed", "submitted", 4010],
        ["flow_completed", "confirmed", 4310],
      ]);
      expect(new Set(events.map((e) => e.props.flow_id)).size).toBe(1);
      expect(events[0].props.flow_id).toMatch(UUID);
      expect(new Set(events.map((e) => e.props.flow_name))).toEqual(new Set(["inbound"]));
      expect(events[2].options).toEqual({ requestId: "req-1" });
      expect(events[3].options).toEqual({ requestId: "req-1" });
    });

    it("the next attempt after a completed one is a new flow with a new id", () => {
      const { result } = renderHook(() => useFlowTelemetry("outbound"));
      result.current.begin();
      result.current.complete();
      result.current.begin();
      const started = sent().filter((e) => e.type === "flow_started");
      expect(started).toHaveLength(2);
      expect(started[0].props.flow_id).not.toBe(started[1].props.flow_id);
    });

    it("an explicit cancel reports the last milestone reached", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.begin();
      result.current.step("validated");
      now += 2_500;
      result.current.cancel();
      expect(sent().at(-1)).toMatchObject({ type: "flow_cancelled", props: { step: "validated", elapsed_ms: 2500 } });
    });
  });

  describe("edge cases", () => {
    it("begin() is idempotent: every focus on the form starts the attempt once", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.begin();
      result.current.begin();
      result.current.begin();
      expect(sent().filter((e) => e.type === "flow_started")).toHaveLength(1);
    });

    it("a step before any focus starts the attempt itself, so the story is never missing its beginning", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.step("validated");
      expect(sent().map((e) => e.type)).toEqual(["flow_started", "flow_step_completed"]);
    });

    it("cancelling a form nobody touched reports nothing", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.cancel();
      expect(trackMock).not.toHaveBeenCalled();
    });

    it("cancel closes the attempt: a second cancel is silent", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.begin();
      result.current.cancel();
      result.current.cancel();
      expect(sent().filter((e) => e.type === "flow_cancelled")).toHaveLength(1);
    });

    it("one blocked submit is one event: the field when one failed, 'multiple' when several, the count of errors", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.validationFailed(["quantity"]);
      result.current.validationFailed(["quantity", "supplier", "other"]);
      result.current.validationFailed(["quantity", "quantity"]);
      expect(sent().filter((e) => e.type === "form_validation_failed").map((e) => [e.props.field, e.props.error_count])).toEqual([
        ["quantity", 1],
        ["multiple", 3],
        ["quantity", 2],
      ]);
    });

    it("repeated blocked submits stay inside the same attempt (they are attempts, not new flows)", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.validationFailed(["quantity"]);
      result.current.validationFailed(["supplier"]);
      expect(new Set(sent().map((e) => e.props.flow_id)).size).toBe(1);
      expect(sent().filter((e) => e.type === "flow_started")).toHaveLength(1);
    });

    it("a failed send leaves the attempt open for the retry: no completion, no cancellation", () => {
      const { result } = renderHook(() => useFlowTelemetry("inbound"));
      result.current.step("validated");
      result.current.step("submitted");
      expect(sent().map((e) => e.type)).toEqual(["flow_started", "flow_step_completed", "flow_step_completed"]);
      result.current.step("submitted");
      expect(new Set(sent().map((e) => e.props.flow_id)).size).toBe(1);
    });
  });
});
