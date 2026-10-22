import { describe, expect, it } from "vitest";

import { ago, money, percent } from "./format";

describe("money", () => {
    it("scales to T, B and M", () => {
        expect(money(2.5e12)).toBe("2.50T");
        expect(money(3.456e9)).toBe("3.46B");
        expect(money(7e6)).toBe("7.00M");
    });

    it("keeps small and negative amounts readable", () => {
        expect(money(1234.5)).toBe("1234.50");
        expect(money(-4.2e9)).toBe("-4.20B");
        expect(money(0)).toBe("0.00");
    });
});

describe("percent", () => {
    it("formats a fraction with the given digits", () => {
        expect(percent(0.125)).toBe("12.5%");
        expect(percent(0.025, 2)).toBe("2.50%");
        expect(percent(-0.2, 0)).toBe("-20%");
    });
});

describe("ago", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");

    it("says just now for a fresh timestamp", () => {
        expect(ago("2026-01-01T11:59:30Z", now)).toBe("just now");
    });

    it("counts minutes, then hours", () => {
        expect(ago("2026-01-01T11:45:00Z", now)).toBe("15 min ago");
        expect(ago("2026-01-01T09:00:00Z", now)).toBe("3.0 h ago");
    });
});
