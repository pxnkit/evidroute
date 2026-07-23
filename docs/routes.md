# Evidence route catalog

| Route | Offline behavior | Cost class | Primary role | Privacy |
| --- | --- | --- | --- | --- |
| Parametric | Deterministic proposal mock | Free | Known-pattern proposal | Local only |
| Episodic memory | Namespace-scoped lookup with aging | Low | User-specific context | Private |
| BM25 | Real sparse ranking | Low | Exact lexical evidence | Local only |
| Dense | Deterministic hashed embeddings | Medium | Paraphrased evidence | Local only |
| Structured | Bounded graph traversal | Medium | Relational and multi-hop facts | Local only |
| Frozen web | Versioned local snapshots | Medium | Temporal external evidence | Public snapshot |
| Live web | Disabled adapter | High | Optional current external evidence | Public only |

The `LIVE_WEB` route is a contract placeholder, not a covert network client. Enabling it in
future work requires an explicit provider, SSRF controls, domain policy, timeouts, content-size
limits, source attribution, and new calibration.

Route selection uses only query features, route probes, source-health snapshots, remaining
budget, and already acquired route IDs. Gold support IDs and forced-route outcomes are confined
to training and evaluation.
