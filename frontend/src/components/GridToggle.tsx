import { useEffect, useState } from "react";

const GRID_KEY = "makerspace.grid";

function applyGrid(on: boolean) {
  // Default is on; we only mark the DOM when the grid is turned OFF.
  document.documentElement.setAttribute("data-grid", on ? "on" : "off");
}

/**
 * Show/hide the blueprint grid background — a "Maker workspace" utility from the
 * design system. Persists the preference locally (server state is untouched).
 */
export function GridToggle() {
  const [on, setOn] = useState<boolean>(
    () => localStorage.getItem(GRID_KEY) !== "off",
  );

  useEffect(() => {
    applyGrid(on);
    localStorage.setItem(GRID_KEY, on ? "on" : "off");
  }, [on]);

  return (
    <button
      className="desk-button"
      type="button"
      aria-pressed={on}
      title={on ? "Hide blueprint grid" : "Show blueprint grid"}
      onClick={() => setOn((current) => !current)}
    >
      {on ? "Grid ON" : "Grid OFF"}
    </button>
  );
}
