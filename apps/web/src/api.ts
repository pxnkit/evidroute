import type { Budget, QueryResponse } from "./types";

export interface QueryPayload {
  query: string;
  mode: "verified" | "best_effort";
  risk_target: number;
  budget: Budget;
  snapshot_id: "t0" | "t1";
  policy: string;
  memory_namespace: string;
}

export async function runQuery(payload: QueryPayload, signal?: AbortSignal): Promise<QueryResponse> {
  const response = await fetch("/api/v1/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Query failed (${response.status}): ${message}`);
  }
  return (await response.json()) as QueryResponse;
}

export async function activateSnapshot(snapshot: "t0" | "t1"): Promise<void> {
  const response = await fetch(`/api/v1/snapshots/activate?snapshot_id=${snapshot}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Could not activate snapshot");
  }
}
