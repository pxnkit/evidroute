# Model card: EvidRoute potential-outcome router

## Summary

The optional learned router is a CPU histogram gradient-boosting regressor over query, task,
snapshot, and route features. It predicts forced-route utility independently for each feasible
route and ranks routes by predicted utility.

## Intended use

Research on heterogeneous evidence routing and controlled offline demonstrations. It is not a
general answer model and not intended for consequential decisions.

## Training data

The bundled checkpoint is generated at runtime from MiniRoute forced-route outcomes. No
checkpoint is committed. Public or private benchmark runs require separate provenance.

## Metrics

The smoke pipeline reports exact match, token F1, supported accuracy, cost, latency, abstention,
route regret, and selective-risk coverage. MiniRoute values only validate the pipeline.

## Limitations and risks

MiniRoute is too small for claims of generalization. Token features may encode dataset-specific
patterns. Utility weights are normative choices. Route outcomes are not independent, and
calibration assumptions can fail under shift. Pickle checkpoints must be loaded only from a
trusted local run.
