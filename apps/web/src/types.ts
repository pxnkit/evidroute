export type RouteName =
  | "PARAMETRIC"
  | "EPISODIC_MEMORY"
  | "BM25"
  | "DENSE"
  | "STRUCTURED"
  | "FROZEN_WEB"
  | "LIVE_WEB";

export interface Budget {
  monetary: number;
  latency_ms: number;
  token_limit: number;
  route_calls: number;
  clarification_turns: number;
}

export interface Candidate {
  route: RouteName;
  feasible: boolean;
  predicted_correct: number;
  predicted_supported: number;
  predicted_action_success: number;
  predicted_contradiction: number;
  predicted_risk: number;
  risk_upper_bound: number;
  expected_cost: number;
  expected_latency_ms: number;
  expected_information_gain: number;
  utility: number;
  source_health: number;
  selected: boolean;
  reason_codes: string[];
}

export interface Evidence {
  evidence_id: string;
  route: RouteName;
  snapshot_id: string;
  source_uri: string;
  title: string;
  text: string;
  retrieval_score: number;
  score_type: string;
  observed_at: string;
  source_updated_at: string | null;
  freshness: string;
  privacy: string;
  integrity_hash: string;
  relation_path: string[];
  unsafe_content: boolean;
  injection_flags: string[];
  metadata: Record<string, unknown>;
}

export interface TraceEvent {
  timestamp: string;
  event_type: string;
  route: RouteName | null;
  message: string;
  measurements: Record<string, unknown>;
}

export interface Decision {
  action: "ANSWER" | "ASK_USER" | "ABSTAIN";
  answer: string | null;
  clarification_question: string | null;
  explanation: string;
  confidence: number;
  risk: number;
  risk_upper_bound: number;
  risk_target: number;
  guarantee_status: string;
  citations: string[];
  unsupported_claims: string[];
  reason_codes: string[];
}

export interface QueryResponse {
  trace_id: string;
  decision: Decision;
  candidates: Candidate[];
  evidence: Evidence[];
  conflicts: Array<Record<string, unknown>>;
  events: TraceEvent[];
  budget_remaining: Budget;
}
