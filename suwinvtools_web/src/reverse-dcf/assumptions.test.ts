import { describe, expect, it } from "vitest";

import type { TickerSnapshot } from "./api";
import { DEFAULTS, buildRequest, terminalMax, withMarginOf, withValidTerminal } from "./assumptions";

const SNAPSHOT: TickerSnapshot = {
    ticker: "NVDA",
    price: 100,
    shares_outstanding: 1000,
    revenue_ttm: 5000,
    fcf_ttm: 1000,
    net_debt: -50,
    as_of: "2026-01-01T00:00:00Z",
    source: "test",
    history: [],
};

describe("withValidTerminal", () => {
    it("lowers a terminal rate that the discount rate has fallen under", () => {
        expect(withValidTerminal({ ...DEFAULTS, discount: 0.02, terminal: 0.025 }).terminal).toBeCloseTo(0.015);
        expect(withValidTerminal({ ...DEFAULTS, discount: 0.025, terminal: 0.025 }).terminal).toBeCloseTo(0.02);
    });

    it("never goes below zero", () => {
        expect(withValidTerminal({ ...DEFAULTS, discount: 0.003, terminal: 0.02 }).terminal).toBe(0);
    });

    it("leaves a valid state alone", () => {
        expect(withValidTerminal(DEFAULTS)).toBe(DEFAULTS);
    });
});

describe("terminalMax", () => {
    it("is capped, and follows a low discount rate", () => {
        expect(terminalMax(0.2)).toBe(0.06);
        expect(terminalMax(0.03)).toBeCloseTo(0.025);
    });
});

describe("withMarginOf", () => {
    it("starts at the margin the company earns today", () => {
        expect(withMarginOf(DEFAULTS, SNAPSHOT).optimizedMargin).toBe(0.2);
    });

    it("stays inside the slider's range", () => {
        expect(withMarginOf(DEFAULTS, { ...SNAPSHOT, fcf_ttm: -100 }).optimizedMargin).toBe(0.01);
        expect(withMarginOf(DEFAULTS, { ...SNAPSHOT, fcf_ttm: 9000 }).optimizedMargin).toBe(0.8);
    });
});

describe("buildRequest", () => {
    it("pins the near-term years in split mode", () => {
        const request = buildRequest(SNAPSHOT, { ...DEFAULTS, mode: "split", splitAfter: 3, nearTermGrowth: 0.2, years: 10 });

        expect(request.growth_segments).toEqual([{ start_year: 1, end_year: 3, growth: 0.2 }]);
        expect(request).toMatchObject({ revenue: 5000, shares_outstanding: 1000, net_debt: -50, current_price: 100, projection_years: 10 });
    });

    it("pins nothing in single mode", () => {
        expect(buildRequest(SNAPSHOT, { ...DEFAULTS, mode: "single" }).growth_segments).toEqual([]);
    });

    it("pins nothing when the split covers the whole horizon", () => {
        expect(buildRequest(SNAPSHOT, { ...DEFAULTS, splitAfter: 5, years: 3 }).growth_segments).toEqual([]);
    });
});
