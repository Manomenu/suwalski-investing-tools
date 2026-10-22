import { useEffect, useState } from "react";

import { isAbort } from "../api/client";

export type Loaded<T> = { kind: "loading" } | { kind: "ready"; data: T } | { kind: "failed"; message: string };

/** Loads once per `key`; the request of a previous key (or of StrictMode's first run) is aborted. */
export function useLoad<T>(key: string, load: (signal: AbortSignal) => Promise<T>): Loaded<T> {
    const [state, setState] = useState<{ key: string; loaded: Loaded<T> }>({ key, loaded: { kind: "loading" } });

    useEffect(() => {
        const controller = new AbortController();
        load(controller.signal)
            .then((data) => {
                setState({ key, loaded: { kind: "ready", data } });
            })
            .catch((error: unknown) => {
                if (isAbort(error) || controller.signal.aborted) return;
                setState({ key, loaded: { kind: "failed", message: error instanceof Error ? error.message : String(error) } });
            });
        return () => {
            controller.abort();
        };
        // `load` is a fresh closure every render; the key is what says the request changed.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]);

    return state.key === key ? state.loaded : { kind: "loading" };
}
