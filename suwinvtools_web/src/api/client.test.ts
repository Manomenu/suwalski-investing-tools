import { describe, expect, it } from "vitest";

import { isAbort, toError } from "./client";

describe("toError", () => {
    it("carries the server's detail", async () => {
        const response = new Response(JSON.stringify({ detail: "not found" }), { status: 404 });

        expect((await toError(response)).message).toBe("not found");
    });

    it("falls back to the status when the body says nothing", async () => {
        const response = new Response("oops", { status: 502, statusText: "Bad Gateway" });

        expect((await toError(response)).message).toBe("502 Bad Gateway");
    });

    it("turns a validation error into field: message", async () => {
        const detail = [{ loc: ["body", "discount_rate"], msg: "Value error, must be above terminal growth" }];
        const response = new Response(JSON.stringify({ detail }), { status: 422 });

        expect((await toError(response)).message).toBe("discount_rate: must be above terminal growth");
    });
});

describe("isAbort", () => {
    it("recognises an aborted request only", () => {
        expect(isAbort(new DOMException("aborted", "AbortError"))).toBe(true);
        expect(isAbort(new Error("boom"))).toBe(false);
    });
});
