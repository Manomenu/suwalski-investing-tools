// This feature's HTTP calls, typed from the generated OpenAPI types.
import { request } from "../api/client";
import type { components } from "../api/openapi";

export type Board = components["schemas"]["Board"];
export type BoardItem = components["schemas"]["BoardItem"];
export type CheckHistory = components["schemas"]["CheckHistory"];
export type Outcome = components["schemas"]["OutcomeOut"];
export type Reading = components["schemas"]["ReadingOut"];
export type Run = components["schemas"]["RunOut"];
export type Verdict = components["schemas"]["Verdict"];

export function fetchBoard(signal: AbortSignal): Promise<Board> {
    return request<Board>("/signals", { signal });
}

export function fetchFeed(verdicts: readonly Verdict[], signal: AbortSignal): Promise<Outcome[]> {
    const query = new URLSearchParams(verdicts.map((verdict) => ["verdict", verdict]));
    return request<Outcome[]>(`/signals/feed?${query.toString()}`, { signal });
}

export function fetchHistory(checkId: string, signal: AbortSignal): Promise<CheckHistory> {
    return request<CheckHistory>(`/signals/${encodeURIComponent(checkId)}`, { signal });
}
