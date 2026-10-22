import { useEffect, useState } from "react";

import { isAbort } from "../api/client";
import { fetchSnapshot, type TickerSnapshot } from "./api";

interface Loaded {
    symbol: string;
    snapshot: TickerSnapshot | null;
    error: string | null;
}

/** The facts of a ticker, fetched again when the symbol changes; a superseded request is aborted. */
export function useSnapshot(symbol: string): { snapshot: TickerSnapshot | null; loading: boolean; error: string | null } {
    const [loaded, setLoaded] = useState<Loaded | null>(null);

    useEffect(() => {
        const controller = new AbortController();
        fetchSnapshot(symbol, controller.signal)
            .then((snapshot) => {
                setLoaded({ symbol, snapshot, error: null });
            })
            .catch((error: unknown) => {
                if (isAbort(error)) return;
                setLoaded({ symbol, snapshot: null, error: error instanceof Error ? error.message : String(error) });
            });
        return () => {
            controller.abort();
        };
    }, [symbol]);

    // Loading is "the answer on screen is not for this symbol yet" — derived, not stored.
    const loading = loaded?.symbol !== symbol;
    return { snapshot: loaded?.snapshot ?? null, loading, error: loading ? null : loaded.error };
}
