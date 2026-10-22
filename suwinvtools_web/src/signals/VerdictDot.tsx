import { ColorSwatch, Tooltip } from "@mantine/core";

import type { Verdict } from "./api";
import { VERDICT_COLOR, VERDICT_LABEL } from "./present";

/** The status light. Its colour is never the only carrier: the tooltip and aria-label name it. */
export function VerdictDot({ verdict }: { verdict: Verdict | null }) {
    const label = verdict === null ? "brak werdyktu" : VERDICT_LABEL[verdict];
    const color = verdict === null ? "gray" : VERDICT_COLOR[verdict];
    return (
        <Tooltip label={label}>
            <ColorSwatch
                component="span"
                aria-label={label}
                size={12}
                color={`var(--mantine-color-${color}-${verdict === "red" || verdict === "green" ? "6" : "7"})`}
                withShadow={false}
                style={verdict === null ? { background: "transparent", outline: "1px solid var(--mantine-color-gray-6)" } : undefined}
            />
        </Tooltip>
    );
}
