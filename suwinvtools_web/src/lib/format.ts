export function money(value: number): string {
    const units: [number, string][] = [
        [1e12, "T"],
        [1e9, "B"],
        [1e6, "M"],
    ];
    for (const [scale, suffix] of units) {
        if (Math.abs(value) >= scale) return `${(value / scale).toFixed(2)}${suffix}`;
    }
    return value.toFixed(2);
}

export const percent = (value: number, digits = 1): string => `${(value * 100).toFixed(digits)}%`;

export function ago(iso: string): string {
    const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
    if (seconds < 90) return "just now";
    if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
    return `${(seconds / 3600).toFixed(1)} h ago`;
}
