import { describe, expect, it } from "vitest";

import { parseRoute, pathFor } from "./route";

describe("parseRoute", () => {
    it("is the board without a panel at /signals", () => {
        expect(parseRoute("/signals")).toEqual({ view: "board", checkId: null });
    });

    it("opens a check's panel at /signals/<id>, whatever the case", () => {
        expect(parseRoute("/signals/a1")).toEqual({ view: "board", checkId: "A1" });
    });

    it("is the timeline at /signals/feed", () => {
        expect(parseRoute("/signals/feed")).toEqual({ view: "feed", checkId: null });
    });

    it("ignores what is not a check id", () => {
        expect(parseRoute("/signals/whatever")).toEqual({ view: "board", checkId: null });
    });
});

describe("pathFor", () => {
    it("round-trips every route", () => {
        for (const path of ["/signals", "/signals/feed", "/signals/B4"]) expect(pathFor(parseRoute(path))).toBe(path);
    });
});
