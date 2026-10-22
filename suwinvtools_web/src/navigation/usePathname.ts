import { useCallback, useSyncExternalStore } from "react";

/** The History API has no event for pushState, so navigate() announces its own changes. */
const NAVIGATED = "navigated";

function subscribe(onChange: () => void): () => void {
    window.addEventListener("popstate", onChange);
    window.addEventListener(NAVIGATED, onChange);
    return () => {
        window.removeEventListener("popstate", onChange);
        window.removeEventListener(NAVIGATED, onChange);
    };
}

const read = (): string => window.location.pathname;

/** The location's pathname, and `navigate` to change it without reloading the page. */
export function usePathname(): { pathname: string; navigate: (to: string, options?: { replace?: boolean }) => void } {
    const pathname = useSyncExternalStore(subscribe, read);
    const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
        if (to === read()) return;
        if (options?.replace) window.history.replaceState(null, "", to);
        else window.history.pushState(null, "", to);
        window.dispatchEvent(new Event(NAVIGATED));
    }, []);
    return { pathname, navigate };
}
