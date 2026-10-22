import { describe, expect, it } from "vitest";

import type { BoardItem } from "./api";
import { columns, formatValue, runLine, sparkPoints } from "./present";

function item(id: string, category: "A" | "B" | "C" | "D" | "E"): BoardItem {
    return {
        check: {
            id,
            category,
            category_name: `kategoria ${category}`,
            title: id,
            question: "?",
            rule_red: "",
            rule_green: "",
            unit: "",
            caveat: "",
        },
        headline: null,
        latest: [],
        spark: [],
    };
}

describe("columns", () => {
    it("groups consecutive checks of a category", () => {
        const result = columns([item("A1", "A"), item("A2", "A"), item("B1", "B")]);

        expect(result.map((column) => [column.category, column.items.map((i) => i.check.id)])).toEqual([
            ["A", ["A1", "A2"]],
            ["B", ["B1"]],
        ]);
    });
});

describe("formatValue", () => {
    it("writes money in Polish scale words", () => {
        expect(formatValue(5.2e9, "USD")).toBe("5.2 mld USD");
    });

    it("keeps a percent unit tight", () => {
        expect(formatValue(39, "% r/r")).toBe("39.0% r/r");
    });

    it("is a dash without a value", () => {
        expect(formatValue(null, "%")).toBe("—");
    });
});

describe("runLine", () => {
    it("says when the job has never run", () => {
        expect(runLine(null)).toContain("nie biegł");
    });

    it("counts the verdicts and the invalid ones", () => {
        const line = runLine({
            id: 1,
            started_at: "2026-11-03T09:00:00+01:00",
            finished_at: null,
            dry_run: false,
            counts: { red: 1, invalid: 2 },
        });

        expect(line).toBe("Run 03.11 · 3 werdyktów · 2 błąd odczytu");
    });
});

describe("sparkPoints", () => {
    it("spans the box from oldest to newest", () => {
        expect(sparkPoints([0, 10], 100, 20)).toBe("0.0,20.0 100.0,0.0");
    });

    it("draws nothing for a single value", () => {
        expect(sparkPoints([3], 100, 20)).toBe("");
    });
});
