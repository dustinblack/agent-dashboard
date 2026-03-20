/**
 * Applies a theme by setting CSS custom properties on the
 * document root element.  Accent colours are always set;
 * slate-scale overrides are applied when the theme provides
 * them and *removed* (so Tailwind defaults kick in) when
 * the theme uses the standard dark palette.
 */

import { THEMES } from './themeValues';
import type { ThemeKey } from './themeValues';

/** All slate custom-property names that may be overridden. */
const SLATE_PROPS = [
  '--color-slate-50',
  '--color-slate-100',
  '--color-slate-200',
  '--color-slate-300',
  '--color-slate-400',
  '--color-slate-500',
  '--color-slate-600',
  '--color-slate-700',
  '--color-slate-800',
  '--color-slate-900',
  '--color-slate-950',
];

/**
 * Apply the given theme to the document root.
 *
 * @param themeKey - One of the six registered theme keys.
 */
export function applyTheme(themeKey: ThemeKey): void {
  const theme = THEMES[themeKey];
  if (!theme) return;

  const root = document.documentElement.style;

  // Accent colours — always set.
  root.setProperty('--color-accent', theme.accent);
  root.setProperty('--color-accent-hover', theme.accentHover);
  root.setProperty('--color-accent-muted', theme.accentMuted);
  root.setProperty('--color-accent-text', theme.accentText);

  // Slate scale — override or remove.
  if (theme.slateScale) {
    for (const prop of SLATE_PROPS) {
      const value = theme.slateScale[prop];
      if (value) {
        root.setProperty(prop, value);
      }
    }
  } else {
    for (const prop of SLATE_PROPS) {
      root.removeProperty(prop);
    }
  }
}
