// Where in the signals tool a path points: the board or the timeline, and the check whose
// panel is open. /signals, /signals/feed, /signals/A1 — the last is what Discord links to.

type View = "board" | "feed";

export interface SignalsRoute {
    view: View;
    checkId: string | null;
}

const CHECK_ID = /^[A-Za-z]\d+$/;

export function parseRoute(path: string): SignalsRoute {
    const parts = path.split("/").filter(Boolean);
    const rest = parts[0] === "signals" ? parts.slice(1) : [];
    if (rest[0] === "feed") return { view: "feed", checkId: null };
    const candidate = rest[0];
    return { view: "board", checkId: candidate !== undefined && CHECK_ID.test(candidate) ? candidate.toUpperCase() : null };
}

export function pathFor(route: SignalsRoute): string {
    if (route.view === "feed") return "/signals/feed";
    return route.checkId === null ? "/signals" : `/signals/${route.checkId}`;
}
