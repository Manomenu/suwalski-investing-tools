import { describe, expect, it } from "vitest";

import type { HistoryPoint, YearProjection } from "./api";
import { CHART_BOX, historyBars, historySeries, plotHeight, projectionBars } from "./chart";

const year = (n: number, fcf: number, source: YearProjection["source"] = "solved"): YearProjection => ({
    year: n,
    growth: 0.1,
    source,
    revenue: 1,
    fcf_margin: 0.1,
    fcf,
    discount_factor: 1,
    present_value: fcf,
});

const point = (n: number, margin: number, growth: number | null): HistoryPoint => ({
    year: n,
    revenue: 100,
    fcf: 10,
    fcf_margin: margin,
    revenue_growth: growth,
});

describe("projectionBars", () => {
    it("makes the tallest bar fill the plot and the others proportional", () => {
        const { bars, max } = projectionBars([year(1, 50, "input"), year(2, 100)], CHART_BOX);

        expect(max).toBe(100);
        expect(bars[1]?.height).toBeCloseTo(plotHeight(CHART_BOX));
        expect(bars[0]?.height).toBeCloseTo(plotHeight(CHART_BOX) / 2);
        expect(bars[0]?.source).toBe("input");
    });

    it("stands every bar on the baseline", () => {
        const { bars } = projectionBars([year(1, 10), year(2, 40)], CHART_BOX);

        for (const bar of bars) expect(bar.y + bar.height).toBeCloseTo(CHART_BOX.height - CHART_BOX.bottom);
    });

    it("draws nothing for a company without positive cash flow", () => {
        const { bars } = projectionBars([year(1, -5), year(2, 0)], CHART_BOX);

        expect(bars.map((bar) => bar.height)).toEqual([0, 0]);
    });

    it("keeps a bar inside its slot and caps its width", () => {
        const { bars } = projectionBars([year(1, 1)], CHART_BOX);

        expect(bars[0]?.width).toBe(72);
        expect(bars[0]?.x).toBeGreaterThanOrEqual(bars[0]?.slotX ?? Infinity);
    });
});

describe("historySeries", () => {
    it("skips years without a value for the measure", () => {
        const points = [point(2020, 0.1, null), point(2021, 0.2, 0.3)];

        expect(historySeries(points, "growth").map((entry) => entry.point.year)).toEqual([2021]);
        expect(historySeries(points, "margin").map((entry) => entry.value)).toEqual([0.1, 0.2]);
    });
});

describe("historyBars", () => {
    it("puts positive bars above the zero line and negative ones below", () => {
        const series = historySeries([point(2020, 0.2, 0.2), point(2021, -0.1, -0.1)], "margin");
        const { bars, zeroY, top, bottom } = historyBars(series, CHART_BOX);

        expect(top).toBe(0.2);
        expect(bottom).toBe(-0.1);
        expect(bars[0]?.y).toBeLessThan(zeroY);
        expect((bars[0]?.y ?? 0) + (bars[0]?.height ?? 0)).toBeCloseTo(zeroY);
        expect(bars[1]?.y).toBeCloseTo(zeroY);
    });

    it("puts the zero line on the baseline when nothing is negative", () => {
        const { zeroY } = historyBars(historySeries([point(2020, 0.2, null)], "margin"), CHART_BOX);

        expect(zeroY).toBeCloseTo(CHART_BOX.height - CHART_BOX.bottom);
    });
});
