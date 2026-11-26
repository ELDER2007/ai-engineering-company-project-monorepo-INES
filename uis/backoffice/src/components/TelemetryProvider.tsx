"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useReportWebVitals } from "next/web-vitals";
import { track } from "@/lib/telemetry";
import { componentForPath, sectionForPath } from "@/lib/telemetry/paths";
import { reportWebVital, setLandingPath } from "@/lib/telemetry/webVitals";

// At most this many unhandled-error events per minute: a render loop or a dead network must not flood the queue.
const MAX_ERRORS_PER_MINUTE = 10;

/**
 * Mounted once in the root layout. It owns what is global to the capture: the unhandled-error listeners, the Web Vitals and the
 * page view of each navigation (the flush when the page is hidden or closed belongs to the service, which starts itself). Everything else is captured where
 * it happens and goes through `track()`.
 */
export default function TelemetryProvider() {
  const pathname = usePathname();
  const lastView = useRef<string | null>(null);
  useReportWebVitals(reportWebVital); // a module-level function: a new identity per render would report every metric again
  setLandingPath(pathname); // only the first call sticks: the page this load landed on

  useEffect(() => {
    let windowStart = Date.now();
    let count = 0;
    const report = () => {
      const component = componentForPath(window.location.pathname);
      if (!component) return; // the contract has no component for the rest of the shell: not reported, not invented
      if (Date.now() - windowStart > 60_000) {
        windowStart = Date.now();
        count = 0;
      }
      if (count >= MAX_ERRORS_PER_MINUTE) return;
      count += 1;
      track("application_error_occurred", { error_code: "unhandled_exception", component });
    };
    window.addEventListener("error", report);
    window.addEventListener("unhandledrejection", report);
    return () => {
      window.removeEventListener("error", report);
      window.removeEventListener("unhandledrejection", report);
    };
  }, []);

  // One `section_viewed` per logical navigation, not per render, hydration or Strict Mode double effect
  // (the ref survives the simulated remount). Coming back to a page later is a new visit.
  useEffect(() => {
    if (lastView.current === pathname) return;
    lastView.current = pathname;
    const section = sectionForPath(pathname);
    if (section) track("section_viewed", { section, locale: "es" });
  }, [pathname]);

  return null;
}
