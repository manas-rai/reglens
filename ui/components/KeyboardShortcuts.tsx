"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const NAV_KEYS: Record<string, { path: string; label: string }> = {
  d: { path: "/", label: "Dashboard" },
  r: { path: "/runs", label: "Runs" },
  p: { path: "/policies", label: "Policies" },
  s: { path: "/settings", label: "Settings" },
  n: { path: "/runs/new", label: "New run" },
};

function isEditable(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    el.isContentEditable
  );
}

export function KeyboardShortcuts() {
  const router = useRouter();
  const [helpOpen, setHelpOpen] = useState(false);
  const [awaitingG, setAwaitingG] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isEditable(e.target)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "?") {
        e.preventDefault();
        setHelpOpen((v) => !v);
        return;
      }
      if (e.key === "Escape") {
        setHelpOpen(false);
        setAwaitingG(false);
        return;
      }
      if (e.key === "g") {
        setAwaitingG(true);
        setTimeout(() => setAwaitingG(false), 1500);
        return;
      }
      if (awaitingG) {
        const target = NAV_KEYS[e.key.toLowerCase()];
        if (target) {
          e.preventDefault();
          router.push(target.path);
        }
        setAwaitingG(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [awaitingG, router]);

  return (
    <>
      {awaitingG && <div className="keychord">g _</div>}
      {helpOpen && (
        <div
          className="keyhelp-backdrop"
          onClick={() => setHelpOpen(false)}
        >
          <div className="keyhelp" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginTop: 0 }}>Keyboard shortcuts</h2>
            <table className="risk-table">
              <tbody>
                {Object.entries(NAV_KEYS).map(([k, v]) => (
                  <tr key={k}>
                    <td>
                      <kbd>g</kbd> <kbd>{k}</kbd>
                    </td>
                    <td>Go to {v.label}</td>
                  </tr>
                ))}
                <tr>
                  <td>
                    <kbd>?</kbd>
                  </td>
                  <td>Toggle this help</td>
                </tr>
                <tr>
                  <td>
                    <kbd>Esc</kbd>
                  </td>
                  <td>Close help</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
