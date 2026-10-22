import type { ReactNode } from "react";

import { CHART_BOX } from "./chart";

const TEXT = {
    fontSize: 11,
    fill: "var(--mantine-color-dimmed)",
    fontFamily: "var(--mantine-font-family-monospace)",
} as const;

/** The SVG canvas shared by the charts; it scales to the width of its container. */
export function SvgChart({ label, children }: { label: string; children: ReactNode }) {
    return (
        <svg viewBox={`0 0 ${CHART_BOX.width} ${CHART_BOX.height}`} width="100%" role="group" aria-label={label}>
            {children}
        </svg>
    );
}

/** A horizontal line across the plot at `y`. */
export function GridLine({ y, strong = false }: { y: number; strong?: boolean }) {
    return (
        <line
            x1={CHART_BOX.left}
            x2={CHART_BOX.width - CHART_BOX.right}
            y1={y}
            y2={y}
            stroke={strong ? "var(--mantine-color-dark-3)" : "var(--mantine-color-default-border)"}
            strokeWidth={1}
        />
    );
}

/** A value on the vertical axis, right-aligned against the plot. */
export function AxisLabel({ y, children }: { y: number; children: ReactNode }) {
    return (
        <text x={CHART_BOX.left - 8} y={y} textAnchor="end" dominantBaseline="central" {...TEXT}>
            {children}
        </text>
    );
}

/** A label under the plot, centred at `x`. */
export function XLabel({ x, children }: { x: number; children: ReactNode }) {
    return (
        <text x={x} y={CHART_BOX.height - 8} textAnchor="middle" {...TEXT}>
            {children}
        </text>
    );
}
