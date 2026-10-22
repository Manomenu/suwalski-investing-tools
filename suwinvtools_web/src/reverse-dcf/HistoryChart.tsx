import { Stack, Text } from "@mantine/core";
import { useState } from "react";

import type { HistoryPoint } from "./api";
import { CHART_BOX, HISTORY_COLOR, METRIC_LABELS, historyBars, historySeries, type Metric } from "./chart";
import { money, percent } from "./format";
import { Readout } from "./Readout";
import { AxisLabel, GridLine, SvgChart, XLabel } from "./SvgChart";

/** Reported years for one measure. A single series, so no legend and one colour — the
 *  sign is carried by which side of the zero line a bar sits on, never by hue. */
export function HistoryChart({ points, metric }: { points: HistoryPoint[]; metric: Metric }) {
    const [hovered, setHovered] = useState<number | null>(null);
    const series = historySeries(points, metric);

    if (series.length === 0) {
        return (
            <Text c="dimmed" ta="center" py="xl">
                no reported years for this company yet
            </Text>
        );
    }

    const { bars, zeroY, top, bottom } = historyBars(series, CHART_BOX);
    const baseline = CHART_BOX.height - CHART_BOX.bottom;
    const active = series.find((entry) => entry.point.year === hovered) ?? null;

    return (
        <Stack gap="md">
            <SvgChart label={`${METRIC_LABELS[metric]} by reported year`}>
                <GridLine y={CHART_BOX.top} />
                <GridLine y={zeroY} strong />
                <AxisLabel y={CHART_BOX.top}>{percent(top, 0)}</AxisLabel>
                <AxisLabel y={bottom < 0 ? baseline : zeroY}>{bottom < 0 ? percent(bottom, 0) : "0%"}</AxisLabel>
                {bars.map((bar, index) => {
                    const entry = series[index];
                    if (!entry) return null;
                    return (
                        <g
                            key={bar.key}
                            tabIndex={0}
                            role="img"
                            aria-label={`FY${bar.key}: ${percent(entry.value)}`}
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
                            <rect
                                x={bar.slotX}
                                y={CHART_BOX.top}
                                width={bar.slotWidth}
                                height={baseline - CHART_BOX.top}
                                fill="transparent"
                            />
                            <rect x={bar.x} y={bar.y} width={bar.width} height={bar.height} rx={3} fill={HISTORY_COLOR} />
                            <XLabel x={bar.slotX + bar.slotWidth / 2}>{`'${String(bar.key).slice(2)}`}</XLabel>
                        </g>
                    );
                })}
            </SvgChart>
            <Readout
                hint={`${series.length} reported ${series.length === 1 ? "year" : "years"} — hover one for its revenue and cash flow`}
                cells={
                    active
                        ? [
                              [`FY${active.point.year}`, METRIC_LABELS[metric]],
                              [METRIC_LABELS[metric], percent(active.value, 1)],
                              ["Revenue", money(active.point.revenue)],
                              ["FCF", money(active.point.fcf)],
                          ]
                        : null
                }
            />
        </Stack>
    );
}
