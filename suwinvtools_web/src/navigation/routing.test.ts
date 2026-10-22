import { describe, expect, it } from "vitest";

import { isToolPath, toolFor } from "./routing";

const PATHS = ["/signals", "/reverse-dcf"];

describe("toolFor", () => {
    it("finds the tool of an exact path", () => {
        expect(toolFor("/reverse-dcf", PATHS)).toBe("/reverse-dcf");
    });

    it("finds the tool of a path below it", () => {
        expect(toolFor("/signals/A1", PATHS)).toBe("/signals");
    });

    it("sends / and unknown paths to the first tool", () => {
        expect(toolFor("/", PATHS)).toBe("/signals");
        expect(toolFor("/nowhere", PATHS)).toBe("/signals");
    });

    it("does not match a path that only shares a prefix", () => {
        expect(toolFor("/reverse-dcf-old", PATHS)).toBe("/signals");
    });

    it("needs at least one tool", () => {
        expect(() => toolFor("/", [])).toThrow();
    });
});

describe("isToolPath", () => {
    it("is true for tool locations and false for the rest", () => {
        expect(isToolPath("/signals", PATHS)).toBe(true);
        expect(isToolPath("/reverse-dcf/x", PATHS)).toBe(true);
        expect(isToolPath("/", PATHS)).toBe(false);
        expect(isToolPath("/nowhere", PATHS)).toBe(false);
    });
});
