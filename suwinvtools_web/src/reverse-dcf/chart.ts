import type { HistoryPoint, Source, YearProjection } from "./api";

/** The drawing area of a chart, in SVG user units; the SVG scales to its container. */
export interface ChartBox {
    width: number;
    height: number;
    left: number;
    right: number;
    top: number;
    bottom: number;
}

export const CHART_BOX: ChartBox = { width: 640, height: 260, left: 64, right: 8, top: 10, bottom: 26 };

/** Series colours, from the Mantine theme so they follow it: the years the user pinned and the years the solver filled in. */
export const SERIES_COLOR: Record<Source, string> = {
    input: "var(--mantine-color-blue-4)",
    solved: "var(--mantine-color-orange-4)",
};

/** The one colour of the history charts: the theme's primary. */
export const HISTORY_COLOR = "var(--mantine-primary-color-filled)";

/** A bar never grows wider than this, however few there are. */
const MAX_BAR_WIDTH = 72;
const BAR_GAP = 2;

interface Bar {
    /** The year it stands for. */
    key: number;
    /** The full-height slot the bar sits in: the hover and focus target. */
    slotX: number;
    slotWidth: number;
    x: number;
    y: number;
    width: number;
    height: number;
}

export const plotHeight = (box: ChartBox): number => box.height - box.top - box.bottom;

/** Horizontal placement of bar `index` of `count`, centred in its equal slot. */
function slotAt(index: number, count: number, box: ChartBox): { slotX: number; slotWidth: number; x: number; width: number } {
    const slotWidth = (box.width - box.left - box.right) / count;
    const width = Math.min(MAX_BAR_WIDTH, slotWidth - BAR_GAP);
    const slotX = box.left + index * slotWidth;
    return { slotX, slotWidth, x: slotX + (slotWidth - width) / 2, width };
}

export interface ProjectionBar extends Bar {
    source: Source;
}

/** FCF per projected year as bars growing up from the baseline; the tallest fills the plot. */
export function projectionBars(years: readonly YearProjection[], box: ChartBox): { bars: ProjectionBar[]; max: number } {
    const max = Math.max(...years.map((year) => year.fcf), 0);
    const baseline = box.height - box.bottom;
    const bars = years.map((year, index) => {
        const height = max > 0 ? (Math.max(0, year.fcf) / max) * plotHeight(box) : 0;
        return { ...slotAt(index, years.length, box), key: year.year, source: year.source, y: baseline - height, height };
    });
    return { bars, max };
}

export type Metric = "margin" | "growth";

export const METRIC_LABELS: Record<Metric, string> = {
    margin: "FCF margin",
    growth: "Revenue growth",
};

export interface HistoryEntry {
    point: HistoryPoint;
    value: number;
}

/** The reported years that have a value for this measure (the oldest has no growth), oldest first. */
export function historySeries(points: readonly HistoryPoint[], metric: Metric): HistoryEntry[] {
    const series: HistoryEntry[] = [];
    for (const point of points) {
        const value = metric === "margin" ? point.fcf_margin : point.revenue_growth;
        if (value !== null && value !== undefined) series.push({ point, value });
    }
    return series;
}

export interface HistoryLayout {
    bars: Bar[];
    /** Where the zero line sits. */
    zeroY: number;
    top: number;
    bottom: number;
}

/** Bars for a measure that can be negative: the sign is the side of the zero line a bar is on. */
export function historyBars(series: readonly HistoryEntry[], box: ChartBox): HistoryLayout {
    const values = series.map((entry) => entry.value);
    const top = Math.max(0, ...values);
    const bottom = Math.min(0, ...values);
    const span = top - bottom || 1;
    const scale = plotHeight(box) / span;
    const zeroY = box.top + top * scale;
    const bars = series.map((entry, index) => {
        const height = Math.abs(entry.value) * scale;
        return { ...slotAt(index, series.length, box), key: entry.point.year, y: entry.value >= 0 ? zeroY - height : zeroY, height };
    });
    return { bars, zeroY, top, bottom };
}
