# Related work and design synthesis

EvidRoute is an original implementation inspired by research directions in the four
manuscripts below. It is not an official reproduction, and no source implementation, private
data, or reported experimental result from those works was copied into this repository.

- Moskvoretskii et al., *Adaptive Retrieval without Self-Knowledge? Bringing Uncertainty Back
  Home* (ACL 2025), motivates explicit comparison between adaptive retrieval and uncertainty
  estimation, including efficiency rather than answer quality alone.
- Wu et al., *Search Wisely* (EMNLP 2025), frames over-search and under-search through
  uncertainty. EvidRoute therefore records stop decisions, route costs, and both missed and
  unnecessary acquisition behavior.
- Qian and Liu, *Scent of Knowledge* (NeurIPS 2025), treats iterative retrieval as information
  foraging. EvidRoute's sequential policy uses a transparent information-value term and permits
  multiple evidence acquisitions.
- Shi et al., *τ-Knowledge* (ICML 2026 manuscript), evaluates conversational agents that combine
  unstructured knowledge, tools, policy, and user interaction. EvidRoute includes `ASK_USER`,
  privacy/policy failures, and a local-only archive adapter without redistributing private data.

The distinct research question here is whether a policy can choose among heterogeneous
evidence and interaction sources under an explicit risk target, source shift, and constrained
budget. The key unit of analysis is route regret against forced-route potential outcomes, not
only final exact match.

See `paper/references.bib` for the bibliography and `reports/research_scope.md` for the claim
ledger.
