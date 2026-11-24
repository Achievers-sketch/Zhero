# ADR 0002: Digital twin design

- Status: accepted
- Date: 2026-11-24

## Decisions

- **Location.** The simulator lives in `backend/app/digital_twin/` (not a top-level
  `digital_twin/` folder as in the blueprint layout) so the backend can import it without
  extra packaging. It is a pure module (no database, no I/O) and can be extracted later.
- **Determinism.** `generate_step(seed, step_index, scenario, scenario_step)` is a pure
  function. Each equipment keeps a stored seed and step counter in `twin_state`; sending
  `seed` to `/simulate` makes runs reproducible, and the stored seed makes any run
  reproducible after the fact.
- **Scenario control.** Faults are triggered through `POST /faults` (allow-listed IDs only).
  `/simulate` also accepts an optional `scenario`, which triggers it first, matching the
  blueprint's "scenario optional" wording. One scenario can be active at a time (409
  otherwise); `/reset` clears it.
- **History is never deleted.** Triggering appends a `SIMULATED_FAULT` event; reset marks it
  resolved and appends a `SIMULATION_RESET` event.
- **Simulation invariant in the database.** `reading` and `equipment_event` have a CHECK
  constraint requiring `simulation = true`. Real telemetry is out of scope for the MVP; drop
  the constraint with an explicit migration if that ever changes.
- **Illustrative values.** All nominal values, noise levels, bands and anomaly strengths are
  in `app/digital_twin/config.py` and labelled as synthetic assumptions, not manufacturer
  limits.
- **Timestamps.** Samples from one call are back-dated by `SIMULATION_INTERVAL_S` so the
  newest sample is "now"; stored and returned in UTC.
