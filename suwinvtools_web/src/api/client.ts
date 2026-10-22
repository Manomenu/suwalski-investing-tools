/**
 * What every feature's HTTP calls share: the API's base path, `request`, and the error a
 * response turns into. The calls themselves live with their feature (`<feature>/api.ts`),
 * like the routes on the server; their types come from the generated `openapi.d.ts`.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

/**
 * The sentence a `detail` carries. Domain refusals answer `{"detail": "a sentence"}`; pydantic
 * validation (422) answers `{"detail": [{loc, msg}, ...]}`, which becomes "field: message" so the
 * user reads the actual problem instead of "Unprocessable Content".
 */
function describeDetail(detail: unknown): string | null {
    if (typeof detail === "string") return detail;
    if (!Array.isArray(detail) || detail.length === 0) return null;
    return (detail as { loc?: unknown; msg?: unknown }[])
        .map((item) => {
            const field = Array.isArray(item.loc) ? (item.loc as unknown[]).at(-1) : undefined;
            const message = (typeof item.msg === "string" ? item.msg : "invalid value").replace(/^Value error, /, "");
            return typeof field === "string" && field !== "body" ? `${field}: ${message}` : message;
        })
        .join("; ");
}

/** The error a failed response carries: the server's `detail` when it sent one. */
export async function toError(response: Response): Promise<Error> {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    return new Error(describeDetail(body?.detail) ?? `${response.status} ${response.statusText}`);
}

/** True for the rejection of a request that an effect's cleanup aborted — not an error to show. */
export function isAbort(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError";
}

/** A JSON call to the API: the parsed body, or the error the response carries. */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${BASE}${path}`, {
        ...init,
        headers: init.body === undefined ? {} : { "content-type": "application/json" },
    });
    if (!response.ok) throw await toError(response);
    return (response.status === 204 ? undefined : await response.json()) as T;
}
