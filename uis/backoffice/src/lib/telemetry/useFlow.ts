"use client";

// The life of one form attempt as telemetry (plan, section 11): `flow_started` at the first interaction, a step
// per milestone (form -> validated -> submitted -> confirmed), `flow_completed` on the backend's confirmation,
// `flow_cancelled` when the user leaves explicitly. An attempt that just stops is NOT an event: abandonment is
// derived later from the missing end. It owns the `flow_id` and the monotonic clock, so a component only says
// what happened. Everything goes through `track()`.
import { useCallback, useRef } from "react";
import type { FlowName, FlowStep, TelemetryEvents } from "./events";
import { uuidV4 } from "./ids";
import { track } from "./index";

type FormField = TelemetryEvents["form_validation_failed"]["field"];

interface Flow {
  id: string;
  startedAt: number;
  lastStep: FlowStep;
}

const monotonic = () => performance.now();

export function useFlowTelemetry(flowName: FlowName) {
  const flow = useRef<Flow | null>(null);

  /** First real interaction with the form. Idempotent: calling it on every focus starts the attempt once. */
  const begin = useCallback(() => {
    if (flow.current) return flow.current;
    flow.current = { id: uuidV4(), startedAt: monotonic(), lastStep: "form" };
    track("flow_started", { flow_id: flow.current.id, flow_name: flowName, step: "form", elapsed_ms: 0 });
    return flow.current;
  }, [flowName]);

  const elapsed = (f: Flow) => Math.round(monotonic() - f.startedAt);

  /** A milestone reached. `requestId` is the one sent as `X-Request-ID` when the step is the HTTP submission. */
  const step = useCallback(
    (name: Exclude<FlowStep, "form" | "confirmed">, requestId?: string) => {
      const f = begin();
      f.lastStep = name;
      track("flow_step_completed", { flow_id: f.id, flow_name: flowName, step: name, elapsed_ms: elapsed(f) }, { requestId });
    },
    [begin, flowName],
  );

  /** The backend confirmed the result and the user can see it. The next interaction starts a new attempt. */
  const complete = useCallback(
    (requestId?: string) => {
      const f = begin();
      track("flow_completed", { flow_id: f.id, flow_name: flowName, step: "confirmed", elapsed_ms: elapsed(f) }, { requestId });
      flow.current = null;
    },
    [begin, flowName],
  );

  /** Explicit cancellation (a "Volver" link). Nothing to report if the user never touched the form. */
  const cancel = useCallback(() => {
    const f = flow.current;
    if (!f) return;
    track("flow_cancelled", { flow_id: f.id, flow_name: flowName, step: f.lastStep, elapsed_ms: elapsed(f) });
    flow.current = null;
  }, [flowName]);

  /** A submit blocked by the form's own validation, before any HTTP request. Counts the submit, not each error. */
  const validationFailed = useCallback(
    (fields: FormField[]) => {
      const f = begin();
      const unique = [...new Set(fields)];
      track("form_validation_failed", {
        flow_id: f.id,
        flow_name: flowName,
        field: unique.length === 1 ? unique[0] : "multiple",
        error_count: fields.length,
      });
    },
    [begin, flowName],
  );

  return { begin, step, complete, cancel, validationFailed };
}
