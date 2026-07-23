# ADR 0001: Credential-free offline reference path

- Status: accepted
- Date: 2026-07-23

## Decision

The default system must run without API keys or network access. External web evidence is modeled
with frozen, versioned snapshots; a live route exists only as a disabled typed adapter.

## Consequences

Smoke tests are deterministic, inexpensive, and safe to run in CI. They do not demonstrate live
web performance. A future live provider requires a new threat review, provider-specific
reliability measurements, and recalibration.
