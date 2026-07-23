# Threat model

## Assets

- private memory and optional private benchmark archives;
- user queries, feedback, and local traces;
- evidence integrity and source provenance;
- calibration state, model checkpoints, and experiment claims.

## Trust boundaries

Queries, uploads, retrieved documents, web content, checkpoint files, and benchmark archives are
untrusted. Bundled source code, MiniRoute data, validated configuration, and locally generated
hashes are trusted for the smoke path.

## Principal threats and controls

| Threat | Control |
| --- | --- |
| Prompt injection in evidence | Pattern detection, unsafe flag, evidence/data separation, fail closed |
| Private-memory exfiltration | Route privacy class, default external denial, local-only live-web setting |
| SSRF | No live network route; URL validator rejects credentials and non-public IP targets |
| Path traversal | Resolved-root containment for uploads and archive members |
| Corpus abuse | 5 MiB limit, content-type allowlist, UTF-8 validation, no automatic indexing |
| Stale or contradictory evidence | Snapshot IDs, timestamps, reliability, conflict surfacing |
| Duplicate amplification | Integrity/duplicate-group deduplication before synthesis |
| Silent source degradation | Route health, deterministic shifts, drift alarm, guarantee invalidation |
| Trace tampering or ambiguity | Canonical JSON, integrity hashes, config/source/model versions |
| Unsafe model deserialization | Trusted-local-only checkpoint policy documented in `SECURITY.md` |
| Denial of service | Query length constraints, bounded routes/hops, per-client API rate limit |

## Out of scope

The prototype does not claim hardened multi-tenant isolation, encrypted storage, identity and
access management, production audit retention, adversarially complete injection detection, or
formal correctness of source content.
