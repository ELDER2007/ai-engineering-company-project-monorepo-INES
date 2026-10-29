Add telemetry event capture to the backoffice

The telemetry plan (docs/telemetry) defines what to measure but nothing
captured it, so every decision in it still rested on guesses. Capture the
events of the plan at the moment they happen in the backoffice, queue them
in the browser and send them in batches to a receiver that checks them
against the approved contract. The receiver stores nothing yet: it is a
stub, so persistence can be built behind the same URL without touching the
frontend.

Receiver (services/api/telemetry)
- Add POST /telemetry/events. It takes {"events": [...]}, validates each
  event with the TelemetryEvent Pydantic model and then with the approved
  JSON Schema (Draft 2020-12, format checking on), logs how many events
  arrived and the type of each, and answers 200 with received, accepted
  and rejected. One bad event does not cost the good ones of its batch
- Report only where an event is wrong and which rule it breaks, never the
  value, so a rejection cannot leak an e-mail
- Stamp what a browser cannot be trusted with: userId is the HMAC of the
  verified session's user (null without one) and the source of the events
  the contract pins to the API or the inventory is set by the server
- Read TELEMETRY_ENDPOINT (not used yet) and TELEMETRY_HMAC_KEY; read the
  body whatever its Content-Type, because sendBeacon sends text/plain
  (no CORS preflight)

Inventory (services/api/inventory)
- Add what the plan lists as prerequisites: programme_id, product_category
  and minimum_stock on assets; unit_cost_minor and an opaque supplier_id on
  inbound orders. An asset without programme or category emits no inventory
  events: nothing is invented
- Compute in the order's own transaction what the events need: stock before
  and after, whether the minimum was crossed (strict, not repeated while
  below) and whether the unit cost moved more than 10 % from the weighted
  mean of the last five entries of the same asset, supplier and office
- Refuse a stock or current_stock field in a write body with 422
  direct_stock_write_forbidden instead of ignoring it
- Add the new columns to existing databases at startup (additive ALTER
  TABLE, no backfill)

Capture (uis/backoffice/src/lib/telemetry)
- Add TelemetryService: in-memory queue; the batch leaves at 20 events or
  10 s after the first; navigator.sendBeacon when the page is hidden or
  closed (fetch with keepalive for the events that need the user's
  identity, because a beacon cannot carry Authorization); 3 retries with
  backoff (1, 2, 4 s); the queue is capped at 100 events / 256 KB
- Expose a single public function, track(), with the properties of every
  event typed from the contract, so an undeclared key does not compile.
  The service adds eventId, sessionId, timestamp, schemaVersion, requestId
  and environment; callers never pass them
- Telemetry never breaks the application: every capture path is guarded,
  and a failed start costs the exit flush, never the event
- Read the endpoint from NEXT_PUBLIC_TELEMETRY_ENDPOINT and forward
  /telemetry/* through Next.js, so the browser stays on its own origin
  (no CORS) and it works in a Codespace opened in the browser

Instrumentation (32 of the 41 events of the plan)
- The five mandatory events of the Nexova briefing (inbound_order_created,
  outbound_order_created, stock_threshold_triggered, direct_stock_edit_
  rejected, kit_cost_variance_detected) from the response to a real order,
  in lib/inventory.ts: the screens repeat no rule
- Navigation and flows (page views, section loads, search, the steps of a
  form, validation failures), unhandled errors and the Error Boundary,
  authentication (in login() and register(), not on each page, with the
  reason of a failure taken from the HTTP status and never from what was
  typed), suppliers, incidents and the incident analysis
- At logout, send the events that need the user's identity while the token
  still exists; a batch flushed afterwards would arrive anonymous and be
  refused

Contract 2.1.0
- Add web_vital_reported (LCP, CLS, INP, FCP, TTFB with the section of the
  landing page) as an additive version: the 40 older variants are
  unchanged and 2.0.0 events stay valid. Documented in section 17 of the
  plan and pending review, since it extends an approved contract

Verification
- Add 113 tests to the API (837 pass, 7 expected failures) and 300 to the
  backoffice (851 pass); coverage thresholds of the repo kept
- Run the frontend code against the live API: 12 events in one request,
  all accepted, no personal data in any event
- Run e2e/telemetry.e2e.mjs with a real browser: 32 events in 3 requests,
  all 200 with rejected [], the five mandatory events with their
  properties, one requestId linking the form step, the HTTP call and the
  events of an order
- Build for production and typecheck without errors
- Check the batches in the browser's Network tab: POST /telemetry/events,
  200 OK, {"received": N, "accepted": N, "rejected": []}

Known limits
- The inventory events are emitted by the browser after the API answers,
  not by the server in the transaction: a transactional outbox is the next
  step. Closing the tab before a batch leaves can still lose events
- Consent and the analytic storage policy of the plan (section 11) are
  still to be approved before capture is enabled in production
