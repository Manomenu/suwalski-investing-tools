import { useEffect, useState } from "react";

import { isAbort } from "../api/client";
import { solveReverseDcf, type ReverseDcfResult, type TickerSnapshot } from "./api";
import { buildRequest, type AssumptionState } from "./assumptions";

/** Sliders fire continuously while dragging; one request per rest, not per pixel. */
const SOLVE_DEBOUNCE_MS = 200;

interface Solved {
    result: ReverseDcfResult | null;
    error: string | null;
}

/** The solved growth for the assumptions, re-solved (debounced) whenever they change. */
export function useReverseDcf(snapshot: TickerSnapshot | null, assumptions: AssumptionState): Solved {
    const [solved, setSolved] = useState<Solved>({ result: null, error: null });

    useEffect(() => {
        if (!snapshot) return;
        const controller = new AbortController();
        const timer = setTimeout(() => {
            solveReverseDcf(buildRequest(snapshot, assumptions), controller.signal)
                .then((result) => {
                    setSolved({ result, error: null });
                })
                .catch((error: unknown) => {
                    if (isAbort(error)) return;
                    setSolved({ result: null, error: error instanceof Error ? error.message : String(error) });
                });
        }, SOLVE_DEBOUNCE_MS);
        return () => {
            controller.abort();
            clearTimeout(timer);
        };
    }, [snapshot, assumptions]);

    // Without a company there is nothing to show, whatever an earlier one solved to.
    return snapshot ? solved : { result: null, error: null };
}
