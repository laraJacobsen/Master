import { useEffect, useState } from "react";
import { fetchBuild } from "./api";
import { isStaleBuild } from "./build";
import { Button } from "./ui";

// The lecturer's pages don't poll the lecture status the way the student page does,
// so they ask for the served build now and then (and when the tab comes back into
// view), and offer a reload once it's a newer one than the page was loaded from.
// Not an automatic reload like the student page: setup may be mid-save and the
// projector may hold edits that only live in this tab.

const CHECK_MS = 30_000;

export function UpdateBanner() {
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      if (document.visibilityState !== "visible") return;
      fetchBuild()
        .then(({ build }) => {
          if (!cancelled && isStaleBuild(build)) setStale(true);
        })
        .catch(() => {
          // Unreachable server: ConnectionBanner says so; try again next time.
        });
    };
    check();
    const timer = window.setInterval(check, CHECK_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, []);

  if (!stale) return null;
  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 bottom-4 z-[120] flex animate-pop-in justify-center px-4">
      <div className="flex items-center gap-3 rounded-lg bg-zinc-900 py-2 pr-2 pl-4 text-[13px] font-medium text-white shadow-xl shadow-zinc-950/20">
        <span className="size-1.5 rounded-[2px] bg-brand-400" aria-hidden="true" />
        This page was updated. Reload to get the new version (anything unsaved here is lost).
        <Button size="sm" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    </div>
  );
}
