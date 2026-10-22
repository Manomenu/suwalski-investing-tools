const UNITS: readonly [number, string][] = [
    [1e12, "T"],
    [1e9, "B"],
    [1e6, "M"],
];

/** A money amount in full units as 1.23T / 4.56B / 7.89M, or plain with two decimals below a million. */
export function money(value: number): string {
    for (const [scale, suffix] of UNITS) {
        if (Math.abs(value) >= scale) return `${(value / scale).toFixed(2)}${suffix}`;
    }
    return value.toFixed(2);
}

/** A decimal fraction as a percentage: 0.125 -> "12.5%". */
export const percent = (value: number, digits = 1): string => `${(value * 100).toFixed(digits)}%`;

/** How long ago an ISO timestamp was, coarsely. */
export function ago(iso: string, now = Date.now()): string {
    const seconds = (now - new Date(iso).getTime()) / 1000;
    if (seconds < 90) return "just now";
    if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
    return `${(seconds / 3600).toFixed(1)} h ago`;
}
