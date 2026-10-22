// How verdicts, values and runs read on the page. Rules here, components only show them.
import type { BoardItem, Outcome, Run, Verdict } from "./api";

export const VERDICT_LABEL: Record<Verdict, string> = {
    red: "RED",
    green: "GREEN",
    neutral: "bez sygnału",
    baseline: "punkt odniesienia",
    not_ready: "brak nowych danych",
    invalid: "błąd odczytu",
    unconfirmed: "niepotwierdzone",
};

// Mantine colour names: red and green carry the meaning, everything else stays quiet.
export const VERDICT_COLOR: Record<Verdict, string> = {
    red: "red",
    green: "green",
    neutral: "gray",
    baseline: "gray",
    not_ready: "gray",
    invalid: "orange",
    unconfirmed: "yellow",
};

export interface CategoryColumn {
    category: string;
    name: string;
    items: BoardItem[];
}

/** The board's columns: one per category, in the order the checks come. */
export function columns(items: readonly BoardItem[]): CategoryColumn[] {
    const result: CategoryColumn[] = [];
    for (const item of items) {
        const last = result.at(-1);
        if (last?.category === item.check.category) last.items.push(item);
        else result.push({ category: item.check.category, name: item.check.category_name, items: [item] });
    }
    return result;
}

export function formatValue(value: number | null | undefined, unit: string): string {
    if (value === null || value === undefined) return "—";
    if (unit === "USD") return money(value);
    const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
    return `${value.toFixed(digits)}${unit.startsWith("%") ? "" : " "}${unit}`.trim();
}

function money(value: number): string {
    const scales: [number, string][] = [
        [1e12, " bln"],
        [1e9, " mld"],
        [1e6, " mln"],
    ];
    for (const [scale, suffix] of scales) if (Math.abs(value) >= scale) return `${(value / scale).toFixed(1)}${suffix} USD`;
    return `${value.toFixed(2)} USD`;
}

/** "Run 03.11 · 12 werdyktów · 1 błąd odczytu" — or why there is none yet. */
export function runLine(run: Run | null | undefined): string {
    if (!run) return "Job jeszcze nie biegł — `just signals run`";
    const started = new Date(run.started_at);
    const day = `${String(started.getDate()).padStart(2, "0")}.${String(started.getMonth() + 1).padStart(2, "0")}`;
    const total = Object.values(run.counts).reduce((sum, count) => sum + count, 0);
    const invalid = run.counts["invalid"] ?? 0;
    return `Run ${day} · ${String(total)} werdyktów${invalid ? ` · ${String(invalid)} błąd odczytu` : ""}`;
}

/** The newest outcomes first, then by check. */
export function newestFirst(outcomes: readonly Outcome[]): Outcome[] {
    return [...outcomes].sort((a, b) => b.evaluated_at.localeCompare(a.evaluated_at) || a.check_id.localeCompare(b.check_id));
}

/** Points of a sparkline in a width × height box, oldest left. */
export function sparkPoints(values: readonly number[], width: number, height: number): string {
    if (values.length < 2) return "";
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = high - low || 1;
    return values
        .map((value, index) => {
            const x = (index / (values.length - 1)) * width;
            const y = height - ((value - low) / span) * height;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");
}
