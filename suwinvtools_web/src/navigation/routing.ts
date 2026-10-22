/** Which tool a location belongs to. Plain functions, so the rules are testable without a browser. */

/** True when `pathname` is the tool's path or lies below it (`/signals/A1` belongs to `/signals`). */
function belongsTo(pathname: string, toolPath: string): boolean {
    return pathname === toolPath || pathname.startsWith(`${toolPath}/`);
}

/**
 * The path of the tool that `pathname` belongs to. `/` and unknown paths belong to the first
 * tool: that is the page the app opens on.
 */
export function toolFor(pathname: string, toolPaths: readonly string[]): string {
    const first = toolPaths[0];
    if (first === undefined) throw new Error("no tools to route to");
    return toolPaths.find((path) => belongsTo(pathname, path)) ?? first;
}

/** Whether `pathname` is already a location of some tool, so it needs no redirect. */
export function isToolPath(pathname: string, toolPaths: readonly string[]): boolean {
    return toolPaths.some((path) => belongsTo(pathname, path));
}
