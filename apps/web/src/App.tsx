import { FormEvent, useMemo, useRef, useState } from "react";
import { activateSnapshot, runQuery } from "./api";
import type { Candidate, Evidence, QueryResponse, RouteName } from "./types";

const ROUTE_LABELS: Record<RouteName, string> = {
  PARAMETRIC: "Parametric",
  EPISODIC_MEMORY: "Memory",
  BM25: "Sparse · BM25",
  DENSE: "Dense",
  STRUCTURED: "Structured",
  FROZEN_WEB: "Frozen web",
  LIVE_WEB: "Live web",
};

const EXAMPLES = [
  "According to the latest snapshot, which Dresden venue will host the fictional Elbe AI Systems Workshop?",
  "Who directs the institute that founded Project Atlas?",
  "What does the green station signal mean for ongoing flight work?",
  "What is the user's current default briefing city?",
];

function percentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`metric metric--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RouteCard({ candidate }: { candidate: Candidate }) {
  const selected = candidate.selected;
  return (
    <article className={`route-card ${selected ? "route-card--selected" : ""} ${!candidate.feasible ? "route-card--muted" : ""}`}>
      <div className="route-card__head">
        <div>
          <span className="eyebrow">{selected ? "Selected route" : candidate.feasible ? "Candidate" : "Unavailable"}</span>
          <h3>{ROUTE_LABELS[candidate.route]}</h3>
        </div>
        <div className={`status-dot ${selected ? "status-dot--active" : ""}`} aria-hidden="true" />
      </div>
      <div className="route-card__metrics">
        <Metric label="Support" value={percentage(candidate.predicted_supported)} tone="good" />
        <Metric label="Risk upper" value={percentage(candidate.risk_upper_bound)} tone="risk" />
        <Metric label="Cost" value={`$${candidate.expected_cost.toFixed(3)}`} />
        <Metric label="Latency" value={`${candidate.expected_latency_ms} ms`} />
      </div>
      <div className="utility-row">
        <span>Conservative utility</span>
        <strong>{candidate.utility.toFixed(3)}</strong>
      </div>
      <div className="reason-list">
        {candidate.reason_codes.slice(0, 3).map((reason) => (
          <span key={reason}>{reason.replaceAll("_", " ")}</span>
        ))}
      </div>
    </article>
  );
}

function EvidenceCard({ item, cited }: { item: Evidence; cited: boolean }) {
  return (
    <article className={`evidence-card ${item.unsafe_content ? "evidence-card--unsafe" : ""}`}>
      <div className="evidence-card__meta">
        <span>{ROUTE_LABELS[item.route]}</span>
        <span>{item.snapshot_id.toUpperCase()}</span>
        <span>{item.privacy}</span>
        {cited && <span className="tag tag--cited">Cited</span>}
        {item.unsafe_content && <span className="tag tag--danger">Untrusted</span>}
      </div>
      <h3>{item.title}</h3>
      <blockquote>{item.text}</blockquote>
      {item.relation_path.length > 0 && (
        <div className="relation-path" aria-label="Structured relation path">
          {item.relation_path.map((node, index) => (
            <span key={`${node}-${index}`}>{node}</span>
          ))}
        </div>
      )}
      <div className="evidence-card__foot">
        <span>score {item.retrieval_score.toFixed(3)} · {item.score_type}</span>
        <code>{item.integrity_hash.slice(0, 12)}</code>
      </div>
    </article>
  );
}

export default function App() {
  const [query, setQuery] = useState(EXAMPLES[0]);
  const [mode, setMode] = useState<"verified" | "best_effort">("verified");
  const [risk, setRisk] = useState(0.25);
  const [snapshot, setSnapshot] = useState<"t0" | "t1">("t1");
  const [routeCalls, setRouteCalls] = useState(3);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const selectedRoutes = useMemo(
    () => result?.candidates.filter((candidate) => candidate.selected).map((candidate) => candidate.route) ?? [],
    [result],
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    abortRef.current = new AbortController();
    try {
      const response = await runQuery(
        {
          query,
          mode,
          risk_target: risk,
          snapshot_id: snapshot,
          policy: "evidroute",
          memory_namespace: "demo",
          budget: {
            monetary: 1,
            latency_ms: 3000,
            token_limit: 4096,
            route_calls: routeCalls,
            clarification_turns: 1,
          },
        },
        abortRef.current.signal,
      );
      setResult(response);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "Unknown query error");
    } finally {
      setLoading(false);
    }
  }

  async function switchSnapshot(next: "t0" | "t1") {
    setSnapshot(next);
    try {
      await activateSnapshot(next);
    } catch {
      setError("Snapshot changed locally, but the API activation failed.");
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="EvidRoute home">
          <span className="brand-mark">ER</span>
          <span>
            <strong>EvidRoute</strong>
            <small>research console · offline</small>
          </span>
        </a>
        <nav aria-label="Primary navigation">
          <a className="nav-link nav-link--active" href="#workspace">Workspace</a>
          <a className="nav-link" href="#routes">Routes</a>
          <a className="nav-link" href="#shift-lab">Shift lab</a>
        </nav>
        <div className="system-status"><span /> all local systems nominal</div>
      </header>

      <main>
        <section className="hero" id="workspace">
          <div>
            <p className="kicker">Risk-constrained evidence routing</p>
            <h1>Know when to search.<br />Know when to stop.</h1>
            <p className="hero-copy">
              Route each question across memory, sparse, dense, structured, and frozen sources—
              then answer only when measured support fits the risk budget.
            </p>
          </div>
          <div className="hero-status">
            <div><span>Snapshot</span><strong>{snapshot.toUpperCase()}</strong></div>
            <div><span>Mode</span><strong>{mode === "verified" ? "Verified" : "Best effort"}</strong></div>
            <div><span>Risk target</span><strong>≤ {percentage(risk)}</strong></div>
          </div>
        </section>

        <form className="query-console" onSubmit={submit}>
          <div className="query-console__top">
            <label htmlFor="query">Research query</label>
            <span>{query.length} / 4,000</span>
          </div>
          <textarea
            id="query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={4000}
            rows={3}
            required
          />
          <div className="examples" aria-label="Example questions">
            {EXAMPLES.map((example) => (
              <button type="button" key={example} onClick={() => setQuery(example)}>
                {example}
              </button>
            ))}
          </div>
          <div className="control-grid">
            <fieldset>
              <legend>Verification</legend>
              <div className="segmented">
                <button type="button" className={mode === "verified" ? "active" : ""} onClick={() => setMode("verified")}>Verified</button>
                <button type="button" className={mode === "best_effort" ? "active" : ""} onClick={() => setMode("best_effort")}>Best effort</button>
              </div>
            </fieldset>
            <fieldset>
              <legend>Snapshot</legend>
              <div className="segmented">
                <button type="button" className={snapshot === "t0" ? "active" : ""} onClick={() => switchSnapshot("t0")}>T0 · archive</button>
                <button type="button" className={snapshot === "t1" ? "active" : ""} onClick={() => switchSnapshot("t1")}>T1 · current</button>
              </div>
            </fieldset>
            <label className="range-control">
              <span>Unsupported-answer risk <strong>{percentage(risk)}</strong></span>
              <input type="range" min="0.05" max="0.5" step="0.05" value={risk} onChange={(event) => setRisk(Number(event.target.value))} />
            </label>
            <label className="range-control">
              <span>Route-call budget <strong>{routeCalls}</strong></span>
              <input type="range" min="1" max="5" step="1" value={routeCalls} onChange={(event) => setRouteCalls(Number(event.target.value))} />
            </label>
          </div>
          <div className="query-console__actions">
            <p>Zero credentials · deterministic MiniRoute corpus · trace export enabled</p>
            {loading ? (
              <button className="run-button run-button--cancel" type="button" onClick={() => abortRef.current?.abort()}>Cancel run</button>
            ) : (
              <button className="run-button" type="submit">Run EvidRoute <span>→</span></button>
            )}
          </div>
        </form>

        {error && <div className="error-banner" role="alert">{error}</div>}
        {loading && <div className="loading-line" aria-label="Routing in progress"><span /></div>}

        {result && (
          <>
            <section className={`decision decision--${result.decision.action.toLowerCase()}`}>
              <div>
                <p className="kicker">Terminal decision · {result.decision.guarantee_status.replaceAll("_", " ")}</p>
                <h2>{result.decision.action === "ANSWER" ? result.decision.answer : result.decision.action === "ASK_USER" ? result.decision.clarification_question : "Safely abstained"}</h2>
                <p>{result.decision.explanation}</p>
                <div className="reason-list">
                  {result.decision.reason_codes.map((code) => <span key={code}>{code.replaceAll("_", " ")}</span>)}
                </div>
              </div>
              <div className="decision__metrics">
                <Metric label="Confidence" value={percentage(result.decision.confidence)} tone="good" />
                <Metric label="Measured risk" value={percentage(result.decision.risk)} tone="risk" />
                <Metric label="Upper bound" value={percentage(result.decision.risk_upper_bound)} tone="risk" />
                <Metric label="Trace" value={result.trace_id.slice(0, 8)} />
              </div>
            </section>

            <section className="section-block" id="routes">
              <div className="section-heading">
                <div><p className="kicker">Decision surface</p><h2>Every route, accounted for</h2></div>
                <p>{selectedRoutes.length} route{selectedRoutes.length === 1 ? "" : "s"} acquired · ${(
                  1 - result.budget_remaining.monetary
                ).toFixed(3)} spent</p>
              </div>
              <div className="route-grid">
                {result.candidates.map((candidate) => <RouteCard key={candidate.route} candidate={candidate} />)}
              </div>
            </section>

            <section className="content-grid">
              <div className="section-block">
                <div className="section-heading section-heading--compact">
                  <div><p className="kicker">Normalized evidence</p><h2>Exact spans & provenance</h2></div>
                  <span>{result.evidence.length} items</span>
                </div>
                <div className="evidence-list">
                  {result.evidence.map((item) => (
                    <EvidenceCard key={item.evidence_id} item={item} cited={result.decision.citations.includes(item.evidence_id)} />
                  ))}
                  {result.evidence.length === 0 && <p className="empty-state">No evidence was acquired for this terminal decision.</p>}
                </div>
              </div>

              <aside className="trace-panel">
                <div className="section-heading section-heading--compact">
                  <div><p className="kicker">Auditable trace</p><h2>Replay</h2></div>
                  <a href={`/api/v1/traces/${result.trace_id}/export`}>Export JSON</a>
                </div>
                <ol className="timeline">
                  {result.events.map((event, index) => (
                    <li key={`${event.timestamp}-${index}`}>
                      <span>{index + 1}</span>
                      <div>
                        <strong>{event.event_type.replaceAll("_", " ")}</strong>
                        <p>{event.message}</p>
                        {event.route && <small>{ROUTE_LABELS[event.route]}</small>}
                      </div>
                    </li>
                  ))}
                </ol>
              </aside>
            </section>

            {result.conflicts.length > 0 && (
              <section className="conflict-panel">
                <p className="kicker">Conflict retained</p>
                <h2>Sources disagree; the trace stays explicit.</h2>
                <pre>{JSON.stringify(result.conflicts, null, 2)}</pre>
              </section>
            )}
          </>
        )}

        <section className="shift-lab" id="shift-lab">
          <div>
            <p className="kicker">Source-shift laboratory</p>
            <h2>Break sources on purpose.<br />Measure recovery honestly.</h2>
            <p>Deterministic manifests cover omission, staleness, contradiction, retriever degradation, outage, latency, memory aging, schema drift, duplicate amplification, and prompt injection.</p>
          </div>
          <div className="shift-visual" aria-label="Source health degradation and recovery chart">
            <div className="chart-labels"><span>1.0</span><span>0.5</span><span>0.0</span></div>
            <svg viewBox="0 0 520 210" role="img" aria-label="Stylized source health lines">
              <path d="M18 38 C95 42 120 48 170 47 S255 43 312 48 S401 44 500 46" className="line line--baseline" />
              <path d="M18 42 C110 40 140 54 190 86 S252 170 310 160 S390 112 500 76" className="line line--shift" />
              <line x1="216" y1="20" x2="216" y2="188" className="shift-marker" />
              <text x="224" y="34">shift detected</text>
            </svg>
            <div className="chart-legend"><span><i className="baseline" /> baseline</span><span><i className="shift" /> degraded → recalibrated</span></div>
          </div>
        </section>
      </main>

      <footer>
        <span>EvidRoute 0.1.0</span>
        <span>No hidden chain-of-thought · measured reason codes only</span>
        <a href="https://github.com/pxnkit/evidroute">GitHub ↗</a>
      </footer>
    </div>
  );
}
