import type { SolveRequest, TickerSnapshot } from "./api";

export type GrowthMode = "single" | "split";

export interface AssumptionState {
    mode: GrowthMode;
    optimizedMargin: number;
    nearTermGrowth: number;
    splitAfter: number;
    discount: number;
    terminal: number;
    years: number;
}

export const DEFAULTS: AssumptionState = {
    mode: "split",
    optimizedMargin: 0.35,
    nearTermGrowth: 0.15,
    splitAfter: 3,
    discount: 0.1,
    terminal: 0.025,
    years: 10,
};

export const HORIZONS = [3, 5, 7, 10, 15, 20];
export const SPLIT_AFTER_OPTIONS = [1, 2, 3, 4, 5];

/** Terminal growth stays at least this far below the discount rate. */
const TERMINAL_GAP = 0.005;

/** The highest terminal growth the slider offers, whatever the discount rate. */
const TERMINAL_CAP = 0.06;

/**
 * Terminal growth must stay below the discount rate, and the discount slider can move under a
 * terminal rate that was fine when it was set — the API rejects that pairing, so it never gets sent.
 */
export function withValidTerminal(next: AssumptionState): AssumptionState {
    const ceiling = next.discount - TERMINAL_GAP;
    return next.terminal > ceiling ? { ...next, terminal: Math.max(0, ceiling) } : next;
}

/** The highest terminal growth the slider may reach at this discount rate. */
export const terminalMax = (discount: number): number => Math.min(TERMINAL_CAP, discount - TERMINAL_GAP);

/** Today's FCF margin of the company: where the optimized margin starts. */
export const currentMargin = (snapshot: TickerSnapshot): number => snapshot.fcf_ttm / snapshot.revenue_ttm;

/**
 * Starts the margin at what the company actually earns today. A fixed default is itself an
 * assumption, and a worse one: 35% is unremarkable for NVDA and absurd for a grocery chain
 * running at 2%, where it values three years of cash above the entire market cap and the
 * solver has nothing to solve.
 */
export function withMarginOf(current: AssumptionState, snapshot: TickerSnapshot): AssumptionState {
    const today = Math.round(currentMargin(snapshot) * 1000) / 1000;
    return { ...current, optimizedMargin: Math.min(0.8, Math.max(0.01, today)) };
}

/** The request the solver gets for these assumptions about this company. */
export function buildRequest(snapshot: TickerSnapshot, assumptions: AssumptionState): SolveRequest {
    const { mode, splitAfter, years } = assumptions;
    // Single rate means no pinned years at all — the solver fills the whole horizon.
    const pinned = mode === "split" && splitAfter < years;
    return {
        revenue: snapshot.revenue_ttm,
        optimized_fcf_margin: assumptions.optimizedMargin,
        shares_outstanding: snapshot.shares_outstanding,
        net_debt: snapshot.net_debt,
        discount_rate: assumptions.discount,
        terminal_growth: assumptions.terminal,
        projection_years: years,
        current_price: snapshot.price,
        growth_segments: pinned ? [{ start_year: 1, end_year: splitAfter, growth: assumptions.nearTermGrowth }] : [],
    };
}
