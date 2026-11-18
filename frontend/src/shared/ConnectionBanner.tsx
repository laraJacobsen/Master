import { useEffect, useState } from "react";
import { CONNECTION_EVENT } from "./api";
import type { ConnectionDetail } from "./api";
import { Spinner } from "./ui";

// The live pages poll the server every few seconds. When those calls stop
// getting through (wifi drops in the lecture hall, server restarts), say so
// at the top of the screen instead of silently showing stale numbers -- and
// take it away again on the first call that succeeds. Fed by api.ts (which
// reports when calls start failing or get through again) and the browser's
// own offline event.

type Shown = "none" | "lost" | "recovered";

export function ConnectionBanner() {
  const [shown, setShown] = useState<Shown>(() => (navigator.onLine ? "none" : "lost"));

  useEffect(() => {
    let hideTimer: number | undefined;
    const onConnection = (e: Event) => {
      window.clearTimeout(hideTimer);
      if ((e as CustomEvent<ConnectionDetail>).detail.ok) {
        setShown("recovered");
        hideTimer = window.setTimeout(() => setShown("none"), 2500);
      } else {
        setShown("lost");
      }
    };
    const onOffline = () => {
      window.clearTimeout(hideTimer);
      setShown("lost");
    };
    // Back online doesn't mean the server answers yet -- the next API call
    // (pages poll) settles it; pages that don't poll just drop the banner.
    const onOnline = () => setShown((s) => (s === "lost" ? "none" : s));
    window.addEventListener(CONNECTION_EVENT, onConnection);
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);
    return () => {
      window.removeEventListener(CONNECTION_EVENT, onConnection);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
      window.clearTimeout(hideTimer);
    };
  }, []);

  if (shown === "none") return null;
  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 top-3 z-[120] flex animate-pop-in justify-center px-4">
      <div className="flex items-center gap-2.5 rounded-lg bg-zinc-900 px-4 py-2.5 text-[13px] font-medium text-white shadow-xl shadow-zinc-950/20">
        {shown === "lost" ? (
          <>
            <Spinner className="text-amber-300" />
            Connection lost. Trying to reconnect…
          </>
        ) : (
          <>
            <span className="size-1.5 rounded-[2px] bg-emerald-400" aria-hidden="true" />
            Back online.
          </>
        )}
      </div>
    </div>
  );
}
