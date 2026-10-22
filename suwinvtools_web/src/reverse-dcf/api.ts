// This feature's HTTP calls, typed from the generated OpenAPI types.
import { request } from "../api/client";
import type { components } from "../api/openapi";

type Schemas = components["schemas"];

export type Source = Schemas["YearProjection"]["source"];
export type YearProjection = Schemas["YearProjection"];
export type Projection = Schemas["Projection"];
export type HistoryPoint = Schemas["HistoryPoint"];
export type TickerSnapshot = Schemas["TickerSnapshot"];
export type ReverseDcfResult = Schemas["ReverseDcfResult"];

/** What the screen decides; the margin ramp and the solver's bracket keep the server's defaults. */
export type SolveRequest = Omit<Schemas["ReverseDcfRequest"], "margin_ramp_years" | "growth_lower_bound" | "growth_upper_bound">;

export function fetchSnapshot(ticker: string, signal: AbortSignal): Promise<TickerSnapshot> {
    return request<TickerSnapshot>(`/market/${encodeURIComponent(ticker)}`, { signal });
}

export function solveReverseDcf(body: SolveRequest, signal: AbortSignal): Promise<ReverseDcfResult> {
    return request<ReverseDcfResult>("/valuation/reverse-dcf", { method: "POST", body: JSON.stringify(body), signal });
}
