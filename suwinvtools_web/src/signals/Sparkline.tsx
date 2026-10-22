import { sparkPoints } from "./present";

const WIDTH = 72;
const HEIGHT = 20;

/** The headline subject's values, oldest left — shape only, the number sits beside it. */
export function Sparkline({ values, color }: { values: readonly number[]; color: string }) {
    const points = sparkPoints(values, WIDTH, HEIGHT);
    if (!points) return null;
    return (
        <svg width={WIDTH} height={HEIGHT} viewBox={`-1 -1 ${String(WIDTH + 2)} ${String(HEIGHT + 2)}`} aria-hidden="true">
            <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
        </svg>
    );
}
