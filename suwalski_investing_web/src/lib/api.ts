/** Mirrors the pydantic contracts in suwalski_investing_library/contracts/. */

export type Source = "input" | "solved";

export interface YearProjection {
    year: number;
    growth: number;
    source: Source;
    revenue: number;
    fcf_margin: number;
    fcf: number;
    discount_factor: number;
    present_value: number;
}

export interface Projection {
    years: YearProjection[];
    pv_explicit: number;
    terminal_value: number;
    pv_terminal: number;
    enterprise_value: number;
    equity_value: number;
    intrinsic_value_per_share: number;
    revenue_cagr: number;
}

export interface GrowthSegment {
    start_year: number;
    end_year: number;
    growth: number;
}

export interface ReverseDcfResult {
    implied_growth: number;
    solved_years: number[];
    known_segments: GrowthSegment[];
    implied_revenue_cagr: number;
    current_price: number;
    projection: Projection;
    iterations: number;
    residual_per_share: number;
}

export interface TickerSnapshot {
    ticker: string;
    price: number;
    shares_outstanding: number;
    revenue_ttm: number;
    fcf_ttm: number;
    net_debt: number;
    currency: string | null;
    as_of: string;
    source: string;
}

export interface ReverseDcfRequest {
    revenue: number;
    optimized_fcf_margin: number;
    shares_outstanding: number;
    net_debt: number;
    discount_rate: number;
    terminal_growth: number;
    projection_years: number;
    growth_segments: GrowthSegment[];
    current_price: number;
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${BASE}${path}`, init);
    if (!response.ok) {
        // The API answers every refusal with {"detail": "..."} — a sentence worth showing.
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<T>;
}

export const fetchSnapshot = (ticker: string, signal?: AbortSignal) =>
    call<TickerSnapshot>(`/market/${encodeURIComponent(ticker)}`, { signal });

export const solveReverseDcf = (request: ReverseDcfRequest, signal?: AbortSignal) =>
    call<ReverseDcfResult>("/valuation/reverse-dcf", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
        signal,
    });
