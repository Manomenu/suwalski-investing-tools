import { Divider, Paper, Stack, Table } from "@mantine/core";

import type { Projection } from "./api";
import { SERIES_COLOR } from "./chart";
import { FactList } from "./FactList";
import { money, percent } from "./format";

/** The numbers behind the chart — also the accessible view of the same data. */
export function ProjectionTable({ projection }: { projection: Projection }) {
    const summary: [string, string][] = [
        ["PV of projected years", money(projection.pv_explicit)],
        ["PV of terminal value", money(projection.pv_terminal)],
        ["Enterprise value", money(projection.enterprise_value)],
        ["Equity value", money(projection.equity_value)],
        ["Revenue CAGR", percent(projection.revenue_cagr, 2)],
        ["Intrinsic value / share", projection.intrinsic_value_per_share.toFixed(2)],
    ];

    return (
        <Paper withBorder p="lg">
            <Stack gap="md">
                <Table.ScrollContainer minWidth={420}>
                    <Table ff="monospace" verticalSpacing={6} withRowBorders>
                        <Table.Thead>
                            <Table.Tr>
                                <Table.Th>Yr</Table.Th>
                                <Table.Th ta="right">Growth</Table.Th>
                                <Table.Th ta="right">Revenue</Table.Th>
                                <Table.Th ta="right">FCF</Table.Th>
                                <Table.Th ta="right">PV</Table.Th>
                            </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                            {projection.years.map((year) => (
                                <Table.Tr key={year.year}>
                                    <Table.Td c="dimmed">{year.year}</Table.Td>
                                    <Table.Td ta="right" fw={600} c={SERIES_COLOR[year.source]}>
                                        {percent(year.growth, 2)}
                                    </Table.Td>
                                    <Table.Td ta="right">{money(year.revenue)}</Table.Td>
                                    <Table.Td ta="right">{money(year.fcf)}</Table.Td>
                                    <Table.Td ta="right" c="dimmed">
                                        {money(year.present_value)}
                                    </Table.Td>
                                </Table.Tr>
                            ))}
                        </Table.Tbody>
                    </Table>
                </Table.ScrollContainer>
                <Divider />
                <FactList rows={summary} cols={2} />
            </Stack>
        </Paper>
    );
}
