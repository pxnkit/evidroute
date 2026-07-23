# ADR 0002: Conservative selective risk with explicit shift invalidation

- Status: accepted
- Date: 2026-07-23

## Decision

Answer acceptance uses a one-sided Wilson upper bound on the unsupported-or-incorrect loss.
Calibration metadata names the loss, confidence, sample size, threshold, snapshot, and
guarantee status. Detected source or error-rate shift changes the status to
`unavailable_under_shift`.

## Consequences

The system may abstain more often than a point-estimate threshold. The bound is a transparent
prototype controller, not a universal distribution-free guarantee under arbitrary dependence.
Small or shifted strata require abstention, pooled fallback, or explicit recalibration.
