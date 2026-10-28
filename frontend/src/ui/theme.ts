import { useCallback, useEffect, useState } from "react";

export type ThemePref = "system" | "light" | "dark";

const KEY = "graphy-theme";
const ORDER: ThemePref[] = ["system", "light", "dark"];

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* storage can be blocked (private windows); fall back to the system setting */
  }
  return "system";
}

export function applyTheme(pref: ThemePref): void {
  const root = document.documentElement;
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", pref);
}

/** Call once before the first render so the page never flashes the wrong theme. */
export function initTheme(): void {
  applyTheme(read());
}

export function useTheme(): [ThemePref, () => void] {
  const [pref, setPref] = useState<ThemePref>(read);
  useEffect(() => applyTheme(pref), [pref]);
  const cycle = useCallback(() => {
    setPref((p) => {
      const next = ORDER[(ORDER.indexOf(p) + 1) % ORDER.length];
      try {
        if (next === "system") localStorage.removeItem(KEY);
        else localStorage.setItem(KEY, next);
      } catch {
        /* preference just won't persist */
      }
      return next;
    });
  }, []);
  return [pref, cycle];
}
