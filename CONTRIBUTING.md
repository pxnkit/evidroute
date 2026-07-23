# Contributing to EvidRoute

EvidRoute welcomes focused changes to routing, evaluation, safety, documentation, and the
offline research console. Open an issue before a large architectural change so the experiment
contract and benchmark boundaries stay coherent.

## Development contract

1. Create a branch from `main`.
2. Install Python 3.12 and Node.js 22, then run `make setup`.
3. Add tests for behavior changes. Failure-handling changes need a deterministic
   `failure_injection` test.
4. Run `make lint`, `make typecheck`, `make test`, and `make smoke`.
5. Explain scientific scope, expected behavior, and any reproducibility impact in the pull
   request.

Do not commit credentials, private benchmark archives, benchmark-derived private records,
local traces, generated model checkpoints, or unlicensed datasets. New metrics must identify
the exact dataset, split, seed, configuration hash, and whether the run was actually executed.

By contributing, you agree that your contribution is licensed under the repository's MIT
license.
