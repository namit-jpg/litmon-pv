/** Theme selection: an explicit light/dark choice, or follow the OS. */
export type ThemeChoice = "light" | "dark" | "system";

const STORAGE_KEY = "litmon_theme";

export function storedTheme(): ThemeChoice {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw === "light" || raw === "dark" ? raw : "system";
}

/**
 * Write the choice onto the root element.
 *
 * "system" removes the attribute rather than resolving it, so the CSS
 * prefers-color-scheme block stays in charge and the page follows the OS if it
 * changes while open.
 */
export function applyTheme(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function saveTheme(choice: ThemeChoice) {
  if (choice === "system") localStorage.removeItem(STORAGE_KEY);
  else localStorage.setItem(STORAGE_KEY, choice);
  applyTheme(choice);
}

/** Whichever theme is actually on screen right now. */
export function resolvedTheme(choice: ThemeChoice): "light" | "dark" {
  if (choice !== "system") return choice;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

/**
 * Call before the first paint. Applying the stored choice at import time
 * avoids a flash of the wrong theme while React mounts.
 */
export function initTheme() {
  applyTheme(storedTheme());
}
