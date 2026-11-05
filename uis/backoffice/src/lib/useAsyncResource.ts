import { useCallback, useEffect, useRef, useState } from "react";
import { track } from "./telemetry";
import type { Section } from "./telemetry/events";

/**
 * Loads something from the API when the component mounts and keeps its three states: the `data`, whether it is
 * `loading`, and the `error` message of the last failure (the data it had before stays on screen).
 *
 * - `reload` reads again without touching the screen (after a mutation: the list stays, then updates).
 * - `retry` is for the "Reintentar" button: it goes back to the loading state first, so the page does not show an
 *   empty list ("no hay datos") while the second attempt is in flight.
 * - `setData` / `setError` let the view apply a change it already knows (e.g. one row edited) or report an error of
 *   its own actions in the same banner.
 *
 * With `section`, the first load reports `section_load_completed` once (success or error): the time from the first
 * render of the view to its data being ready or failing, on the monotonic clock. Reloads and retries are not new
 * section loads. (A SPA navigation has no document start; the view's first render is the start we have.)
 *
 * `load` and `describeError` must keep the same identity between renders (module-level functions): they are what
 * `reload` depends on, and a new one on every render would load again on every render.
 */
export function useAsyncResource<T>(
  load: () => Promise<T>,
  initial: T,
  describeError: (err: unknown) => string,
  section?: Section,
) {
  const [data, setData] = useState<T>(initial);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef<number>(performance.now());
  const reported = useRef(false);

  const reportLoad = useCallback(
    (outcome: "success" | "error") => {
      if (!section || reported.current) return;
      reported.current = true;
      track("section_load_completed", { section, duration_ms: Math.max(0, Math.round(performance.now() - startedAt.current)), outcome });
    },
    [section],
  );

  const reload = useCallback(async () => {
    setError(null);
    try {
      setData(await load());
      reportLoad("success");
    } catch (err) {
      setError(describeError(err));
      reportLoad("error");
    } finally {
      setLoading(false);
    }
  }, [load, describeError, reportLoad]);

  const retry = useCallback(async () => {
    setLoading(true);
    await reload();
  }, [reload]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, setData, loading, error, setError, reload, retry };
}
