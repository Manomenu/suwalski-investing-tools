import { Stack } from "@mantine/core";
import { useState } from "react";

import type { YearProjection } from "./api";
import { CHART_BOX, SERIES_COLOR, projectionBars } from "./chart";
import { money, percent } from "./format";
import { Readout } from "./Readout";
import { AxisLabel, GridLine, SvgChart, XLabel } from "./SvgChart";

/** Free cash flow per projected year. Two categories — the years you pinned and the years
 *  the solver filled in — so identity is carried by a legend plus the hover readout, never
 *  by colour alone. */
export function ProjectionChart({ years }: { years: YearProjection[] }) {
    const [hovered, setHovered] = useState<number | null>(null);
    const { bars, max } = projectionBars(years, CHART_BOX);
    const active = years.find((year) => year.year === hovered) ?? null;
    const baseline = CHART_BOX.height - CHART_BOX.bottom;
    const middle = (CHART_BOX.top + baseline) / 2;

    return (
        <Stack gap="md">
            <SvgChart label="Projected free cash flow by year">
                <GridLine y={CHART_BOX.top} />
                <GridLine y={middle} />
                <GridLine y={baseline} strong />
                <AxisLabel y={CHART_BOX.top}>{money(max)}</AxisLabel>
                <AxisLabel y={middle}>{money(max / 2)}</AxisLabel>
                <AxisLabel y={baseline}>0</AxisLabel>
                {bars.map((bar) => (
                    <g
                        key={bar.key}
                        tabIndex={0}
                        role="img"
                        aria-label={`Year ${bar.key}: FCF ${money(years.find((year) => year.year === bar.key)?.fcf ?? 0)}`}
                        onMouseEnter={() => {
                            setHovered(bar.key);
                        }}
                        onMouseLeave={() => {
                            setHovered(null);
                        }}
                        onFocus={() => {
                            setHovered(bar.key);
                        }}
                        onBlur={() => {
                            setHovered(null);
                        }}
                        opacity={hovered !== null && hovered !== bar.key ? 0.45 : 1}
                    >
                        <rect x={bar.slotX} y={CHART_BOX.top} width={bar.slotWidth} height={baseline - CHART_BOX.top} fill="transparent" />
                        <rect x={bar.x} y={bar.y} width={bar.width} height={bar.height} rx={3} fill={SERIES_COLOR[bar.source]} />
                        <XLabel x={bar.slotX + bar.slotWidth / 2}>{bar.key}</XLabel>
                    </g>
                ))}
            </SvgChart>
            <Readout
                hint="hover a year for its revenue, margin and discounted value"
                cells={
                    active
                        ? [
                              [`Year ${active.year}`, active.source === "input" ? "your input" : "solved"],
                              ["Growth", percent(active.growth, 2)],
                              ["Revenue", money(active.revenue)],
                              ["FCF", `${money(active.fcf)} @ ${percent(active.fcf_margin)}`],
                          ]
                        : null
                }
            />
        </Stack>
    );
}
